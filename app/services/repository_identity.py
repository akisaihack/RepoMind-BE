"""Validate that a local Git checkout matches a GitHub repository identity."""

import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

_SCP_GITHUB_URL = re.compile(r"^(?:[^@/]+@)?github\.com:(?P<path>.+)$", re.IGNORECASE)


class RepositoryIdentityError(ValueError):
    """Base error for repository identity lookup and validation failures."""


class GitRemoteError(RepositoryIdentityError):
    """Raised when the local origin remote cannot be identified."""


class RepositoryIdentityLookupError(RepositoryIdentityError):
    """Raised when a GitHub repository identity cannot be found."""


class RepositoryIdentityMismatchError(RepositoryIdentityError):
    """Raised when the local checkout and GitHub repository do not match."""


class QueryClient(Protocol):
    def execute_query(self, query: str, parameters: dict[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class RepositoryIdentity:
    github_repository_id: int
    local_full_name: str | None
    expected_full_name: str | None
    source: str
    skipped: bool = False


class RepositoryIdentityValidator:
    def __init__(
        self,
        neo4j_client: QueryClient,
        github_lookup: Callable[[int], Mapping[str, Any]],
    ) -> None:
        self._neo4j_client = neo4j_client
        self._github_lookup = github_lookup

    def validate(
        self,
        github_repository_id: int,
        repository_path: Path,
        *,
        skip: bool = False,
    ) -> RepositoryIdentity:
        if (
            not isinstance(github_repository_id, int)
            or isinstance(github_repository_id, bool)
            or github_repository_id <= 0
        ):
            raise RepositoryIdentityError("GitHub repository ID must be a positive integer.")
        if skip:
            return RepositoryIdentity(
                github_repository_id=github_repository_id,
                local_full_name=None,
                expected_full_name=None,
                source="skipped",
                skipped=True,
            )

        origin_url = get_origin_url(repository_path)
        local_full_name = normalize_github_repository_url(origin_url)
        expected_full_name, source = self._lookup_expected_identity(github_repository_id)

        if local_full_name.casefold() != expected_full_name.casefold():
            raise RepositoryIdentityMismatchError(
                "Local origin repository does not match githubRepositoryId "
                f"{github_repository_id}: local={local_full_name!r}, "
                f"expected={expected_full_name!r}."
            )

        return RepositoryIdentity(
            github_repository_id=github_repository_id,
            local_full_name=local_full_name,
            expected_full_name=expected_full_name,
            source=source,
        )

    def _lookup_expected_identity(self, github_repository_id: int) -> tuple[str, str]:
        records, _, _ = self._neo4j_client.execute_query(
            """
            MATCH (repository:Repository {githubRepositoryId: $repositoryId})
            RETURN repository.fullName AS fullName
            LIMIT 1
            """,
            {"repositoryId": github_repository_id},
        )
        if records and records[0].get("fullName"):
            return str(records[0]["fullName"]), "neo4j"

        repository = self._github_lookup(github_repository_id)
        actual_id = repository.get("id")
        full_name = repository.get("full_name")
        if actual_id != github_repository_id or not isinstance(full_name, str) or not full_name:
            raise RepositoryIdentityLookupError(
                f"GitHub returned an invalid identity for repository {github_repository_id}."
            )
        return full_name, "github"


def get_origin_url(repository_path: Path) -> str:
    """Return the primary fetch URL for the local checkout's origin remote."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_path), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitRemoteError("Git executable was not found.") from exc
    except subprocess.CalledProcessError as exc:
        raise GitRemoteError(
            "Local repository must have an origin remote for identity validation."
        ) from exc

    origin_url = result.stdout.strip()
    if not origin_url:
        raise GitRemoteError("Local repository origin URL is empty.")
    return origin_url


def normalize_github_repository_url(url: str) -> str:
    """Normalize supported GitHub HTTPS/SSH URLs to owner/repository."""
    value = url.strip()
    scp_match = _SCP_GITHUB_URL.fullmatch(value)
    if scp_match:
        return _normalize_repository_path(scp_match.group("path"))

    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https", "ssh", "git"}:
        raise GitRemoteError(f"Unsupported Git remote URL format: {url!r}.")
    if (parsed.hostname or "").casefold() != "github.com":
        raise GitRemoteError("Only github.com origin remotes are supported.")
    return _normalize_repository_path(parsed.path)


def _normalize_repository_path(path: str) -> str:
    value = path.strip().strip("/")
    if value.lower().endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) != 2 or not all(parts):
        raise GitRemoteError("GitHub origin must identify one owner/repository pair.")
    return f"{parts[0]}/{parts[1]}"
