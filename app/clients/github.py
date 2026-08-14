"""Authenticated GitHub REST API client."""

import logging
from collections.abc import Mapping
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"


class GitHubAPIError(Exception):
    """Base exception for GitHub API failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubRateLimitError(GitHubAPIError):
    """Raised when GitHub rejects a request because its rate limit was exhausted."""

    def __init__(self, reset_at: str | None) -> None:
        message = "GitHub API rate limit exceeded."
        if reset_at:
            message = f"{message} Reset timestamp: {reset_at}."
        super().__init__(message, status_code=429)
        self.reset_at = reset_at


class GitHubClient:
    """Read repository development history through the GitHub REST API."""

    def __init__(
        self,
        token: str,
        owner: str,
        repository: str,
        *,
        base_url: str = GITHUB_API_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token.strip() or not owner.strip() or not repository.strip():
            raise ValueError("GitHub token, owner, and repository must all be configured.")

        self._owner = owner
        self._repository = repository
        self._repository_path = f"/repos/{owner}/{repository}"
        self._http = httpx.Client(
            base_url=base_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "RepoMind-Backend",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            timeout=30.0,
            transport=transport,
        )

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        **kwargs: Any,
    ) -> Self:
        """Create a client from Flask configuration without logging secret values."""
        required_keys = ("GITHUB_TOKEN", "GITHUB_REPOSITORY_OWNER", "GITHUB_REPOSITORY_NAME")
        missing_keys = [key for key in required_keys if not config.get(key)]
        if missing_keys:
            raise ValueError(f"Missing required GitHub configuration: {', '.join(missing_keys)}.")

        return cls(
            token=config["GITHUB_TOKEN"],
            owner=config["GITHUB_REPOSITORY_OWNER"],
            repository=config["GITHUB_REPOSITORY_NAME"],
            **kwargs,
        )

    def get_repository(self) -> dict[str, Any]:
        return self._get(self._repository_path)

    def get_repository_by_id(self, github_repository_id: int) -> dict[str, Any]:
        """Look up a repository by its immutable GitHub database ID."""
        if (
            not isinstance(github_repository_id, int)
            or isinstance(github_repository_id, bool)
            or github_repository_id <= 0
        ):
            raise ValueError("GitHub repository ID must be a positive integer.")
        return self._get(f"/repositories/{github_repository_id}")

    def list_branches(self) -> list[dict[str, Any]]:
        return self._get_paginated(f"{self._repository_path}/branches")

    def list_issues(self) -> list[dict[str, Any]]:
        issues = self._get_paginated(f"{self._repository_path}/issues", {"state": "all"})
        return [issue for issue in issues if "pull_request" not in issue]

    def get_issue(self, number: int) -> dict[str, Any]:
        return self._get(f"{self._repository_path}/issues/{number}")

    def list_pull_requests(self) -> list[dict[str, Any]]:
        return self._get_paginated(f"{self._repository_path}/pulls", {"state": "all"})

    def get_pull_request(self, number: int) -> dict[str, Any]:
        return self._get(f"{self._repository_path}/pulls/{number}")

    def list_pull_request_commits(self, number: int) -> list[dict[str, Any]]:
        return self._get_paginated(f"{self._repository_path}/pulls/{number}/commits")

    def list_pull_request_files(self, number: int) -> list[dict[str, Any]]:
        return self._get_paginated(f"{self._repository_path}/pulls/{number}/files")

    def list_commits(self) -> list[dict[str, Any]]:
        return self._get_paginated(f"{self._repository_path}/commits")

    def get_commit(self, sha: str) -> dict[str, Any]:
        path = f"{self._repository_path}/commits/{sha}"
        response = self._request(path, {"per_page": 100})
        commit = response.json()
        files = list(commit.get("files", []))
        next_url = response.links.get("next", {}).get("url")

        while next_url:
            response = self._request(next_url, None)
            page = response.json()
            files.extend(page.get("files", []))
            next_url = response.links.get("next", {}).get("url")

        commit["files"] = files
        return commit

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get(
        self,
        path_or_url: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        response = self._request(path_or_url, params)
        return response.json()

    def _get_paginated(
        self,
        path_or_url: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_url: str | None = path_or_url
        next_params = {"per_page": 100, **(params or {})}

        while next_url:
            response = self._request(next_url, next_params)
            page = response.json()
            if not isinstance(page, list):
                raise GitHubAPIError("GitHub API returned an invalid paginated response.")
            results.extend(page)
            next_url = response.links.get("next", {}).get("url")
            next_params = None

        return results

    def _request(
        self,
        path_or_url: str,
        params: Mapping[str, Any] | None,
    ) -> httpx.Response:
        try:
            response = self._http.get(path_or_url, params=params)
        except httpx.HTTPError as exc:
            logger.error("GitHub API network request failed; error=%s", type(exc).__name__)
            raise GitHubAPIError("GitHub API network request failed.") from exc

        remaining = response.headers.get("x-ratelimit-remaining")
        if response.status_code in {403, 429} and (
            remaining == "0" or "retry-after" in response.headers
        ):
            reset_at = response.headers.get("x-ratelimit-reset")
            logger.warning("GitHub API rate limit exceeded; reset=%s", reset_at or "unknown")
            raise GitHubRateLimitError(reset_at)

        if response.is_error:
            logger.error(
                "GitHub API request failed; status=%s path=%s",
                response.status_code,
                response.request.url.path,
            )
            raise GitHubAPIError(
                f"GitHub API request failed with status {response.status_code}.",
                status_code=response.status_code,
            )

        return response
