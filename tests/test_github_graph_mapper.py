"""GitHub DTO to Neo4j graph batch mapping tests."""

from app.dtos.github import (
    BranchDTO,
    CommitDTO,
    CommitFileDTO,
    DevelopmentHistoryDTO,
    IssueDTO,
    IssueReferenceDTO,
    PullRequestDTO,
    RepositoryDTO,
)
from app.graph.mappers.github import GitHubGraphMapper


def _file() -> CommitFileDTO:
    return CommitFileDTO(
        filename="app/service.py",
        previous_filename=None,
        status="modified",
        additions=3,
        deletions=1,
        changes=4,
        blob_url=None,
        raw_url=None,
        patch="@@ -1 +1,3 @@",
    )


def _history() -> DevelopmentHistoryDTO:
    return DevelopmentHistoryDTO(
        repository=RepositoryDTO(
            100, "repo", "org/repo", "https://github.com/org/repo", "main", False, None
        ),
        branches=(BranchDTO("main", "abc123", True),),
        issues=(
            IssueDTO(
                7,
                "Issue",
                "open",
                "Body",
                1,
                "octocat",
                "https://github.com/org/repo/issues/7",
                ("bug",),
                (),
                "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:00Z",
                None,
            ),
        ),
        pull_requests=(
            PullRequestDTO(
                9,
                "PR",
                "closed",
                "Closes #7",
                2,
                "developer",
                "https://github.com/org/repo/pull/9",
                "main",
                "feature",
                "abc123",
                "merge123",
                True,
                "2026-08-01T00:00:00Z",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
                ("abc123",),
                (_file(),),
                (IssueReferenceDTO(7, "resolves"),),
            ),
        ),
        commits=(
            CommitDTO(
                "abc123",
                "Change service",
                "https://github.com/org/repo/commit/abc123",
                "Developer",
                2,
                "developer",
                "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:00Z",
                ("parent123",),
                (_file(),),
            ),
        ),
    )


def test_maps_nodes_relationships_and_file_change_id() -> None:
    graph = GitHubGraphMapper().map(
        _history(),
        {("abc123", "app/service.py"): 105},
    )

    assert graph.repositories[0]["githubRepositoryId"] == 100
    assert {node["properties"]["sha"] for node in graph.commits} == {
        "abc123",
        "merge123",
        "parent123",
    }
    assert graph.commit_files[0]["properties"]["fileChangeId"] == 105
    assert graph.pull_request_resolutions == (
        {
            "fromKey": "100:pr:9",
            "toKey": "100:issue:7",
            "properties": {},
        },
    )
    assert {row["toKey"] for row in graph.pull_request_commits} == {
        "100:commit:abc123",
        "100:commit:merge123",
    }
    assert len(graph.developers) == 2
    assert graph.developer_commits[0]["githubId"] == 2


def test_deduplicates_files_and_developers() -> None:
    graph = GitHubGraphMapper().map(_history(), {})

    assert len(graph.files) == 1
    assert len(graph.repository_files) == 1
    assert len(graph.developers) == 2


def test_normalizes_file_keys_shared_by_commit_and_pull_request() -> None:
    history = _history()
    commit_file = history.commits[0].files[0]
    object.__setattr__(commit_file, "filename", r".\app\service.py")

    graph = GitHubGraphMapper().map(history, {})

    assert len(graph.files) == 1
    assert graph.files[0]["key"] == "100:file:app/service.py"
    assert graph.files[0]["properties"]["path"] == "app/service.py"
    assert graph.commit_files[0]["toKey"] == graph.pull_request_files[0]["toKey"]
