"""GitHub REST API client tests."""

import httpx
import pytest

from app.clients.github import GitHubAPIError, GitHubClient, GitHubRateLimitError


def test_github_client_follows_pagination_and_filters_pull_requests() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-token"
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"number": 2, "title": "second issue"}])
        return httpx.Response(
            200,
            json=[
                {"number": 1, "title": "first issue"},
                {"number": 10, "pull_request": {"url": "https://example.test/pulls/10"}},
            ],
            headers={
                "link": (
                    '<https://api.github.test/repos/octocat/Hello-World/issues?page=2>; rel="next"'
                )
            },
        )

    with GitHubClient(
        "test-token",
        "octocat",
        "Hello-World",
        base_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        issues = client.list_issues()

    assert [issue["number"] for issue in issues] == [1, 2]
    assert len(requests) == 2
    assert requests[0].url.params["state"] == "all"
    assert requests[0].url.params["per_page"] == "100"


def test_github_client_combines_paginated_commit_files() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        file_number = request.url.params.get("page", "1")
        payload = {
            "sha": "abc123",
            "files": [{"filename": f"file-{file_number}.py"}],
        }
        if file_number == "1":
            return httpx.Response(
                200,
                json=payload,
                headers={
                    "link": (
                        "<https://api.github.test/repos/octocat/Hello-World/"
                        "commits/abc123?page=2>; "
                        'rel="next"'
                    )
                },
            )
        return httpx.Response(200, json=payload)

    with GitHubClient(
        "test-token",
        "octocat",
        "Hello-World",
        base_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        commit = client.get_commit("abc123")

    assert [file["filename"] for file in commit["files"]] == ["file-1.py", "file-2.py"]


def test_github_client_converts_rate_limit_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "1777777777",
            },
        )

    with GitHubClient(
        "test-token",
        "octocat",
        "Hello-World",
        base_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(GitHubRateLimitError) as exc_info:
            client.get_repository()

    assert exc_info.value.reset_at == "1777777777"


def test_github_client_converts_api_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"message": "Not Found"})
    )

    with GitHubClient(
        "test-token",
        "octocat",
        "missing-repository",
        base_url="https://api.github.test",
        transport=transport,
    ) as client:
        with pytest.raises(GitHubAPIError) as exc_info:
            client.get_repository()

    assert exc_info.value.status_code == 404
    assert "test-token" not in str(exc_info.value)


def test_github_client_rejects_missing_configuration() -> None:
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        GitHubClient.from_config(
            {
                "GITHUB_REPOSITORY_OWNER": "octocat",
                "GITHUB_REPOSITORY_NAME": "Hello-World",
            }
        )
