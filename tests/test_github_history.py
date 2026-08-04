"""GitHub development-history collection tests."""

from typing import Any

from app.services.github_history import GitHubHistoryCollector


class SampleGitHubClient:
    """In-memory octocat/Hello-World API fixture."""

    def get_repository(self) -> dict[str, Any]:
        return {
            "id": 1,
            "name": "Hello-World",
            "full_name": "octocat/Hello-World",
            "html_url": "https://github.com/octocat/Hello-World",
            "default_branch": "main",
            "private": False,
            "description": "Sample repository",
        }

    def list_branches(self) -> list[dict[str, Any]]:
        return [{"name": "main", "commit": {"sha": "abc123"}, "protected": True}]

    def list_issues(self) -> list[dict[str, Any]]:
        return [{"number": 7}]

    def get_issue(self, number: int) -> dict[str, Any]:
        return {
            "number": number,
            "title": "Collect GitHub history",
            "state": "open",
            "body": "Issue body",
            "user": {"login": "octocat"},
            "html_url": f"https://github.com/octocat/Hello-World/issues/{number}",
            "labels": [{"name": "enhancement"}],
            "assignees": [{"login": "developer"}],
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-08-02T00:00:00Z",
            "closed_at": None,
        }

    def list_pull_requests(self) -> list[dict[str, Any]]:
        return [{"number": 3}]

    def get_pull_request(self, number: int) -> dict[str, Any]:
        return {
            "number": number,
            "title": "Add GitHub collector",
            "state": "closed",
            "body": "PR body",
            "user": {"login": "developer"},
            "html_url": f"https://github.com/octocat/Hello-World/pull/{number}",
            "base": {"ref": "main"},
            "head": {"ref": "feature/github", "sha": "abc123"},
            "merge_commit_sha": "merge123",
            "merged": True,
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-08-02T00:00:00Z",
            "closed_at": "2026-08-02T00:00:00Z",
            "merged_at": "2026-08-02T00:00:00Z",
        }

    def list_pull_request_commits(self, number: int) -> list[dict[str, Any]]:
        return [{"sha": "abc123"}]

    def list_pull_request_files(self, number: int) -> list[dict[str, Any]]:
        return [self._file()]

    def list_commits(self) -> list[dict[str, Any]]:
        return [{"sha": "abc123"}]

    def get_commit(self, sha: str) -> dict[str, Any]:
        return {
            "sha": sha,
            "html_url": f"https://github.com/octocat/Hello-World/commit/{sha}",
            "commit": {
                "message": "feat: collect history",
                "author": {"name": "Developer", "date": "2026-08-01T00:00:00Z"},
                "committer": {"date": "2026-08-01T00:00:00Z"},
            },
            "author": {"login": "developer"},
            "parents": [{"sha": "parent123"}],
            "files": [self._file()],
        }

    @staticmethod
    def _file() -> dict[str, Any]:
        return {
            "filename": "app/clients/github.py",
            "status": "added",
            "additions": 10,
            "deletions": 0,
            "changes": 10,
            "blob_url": "https://github.com/blob/abc123/app/clients/github.py",
            "raw_url": "https://github.com/raw/abc123/app/clients/github.py",
            "patch": "@@ -0,0 +1,10 @@",
        }


def test_collects_sample_repository_development_history() -> None:
    history = GitHubHistoryCollector(SampleGitHubClient()).collect()  # type: ignore[arg-type]

    assert history.repository.full_name == "octocat/Hello-World"
    assert history.branches[0].sha == "abc123"
    assert history.issues[0].number == 7
    assert history.issues[0].labels == ("enhancement",)
    assert history.pull_requests[0].commit_shas == ("abc123",)
    assert history.pull_requests[0].files[0].filename == "app/clients/github.py"
    assert history.commits[0].parent_shas == ("parent123",)
    assert history.commits[0].files[0].additions == 10
