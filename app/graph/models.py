"""Database-neutral batches consumed by the Neo4j repository."""

from dataclasses import dataclass
from typing import Any

GraphRow = dict[str, Any]


@dataclass(frozen=True, slots=True)
class GitHubGraphData:
    repositories: tuple[GraphRow, ...] = ()
    branches: tuple[GraphRow, ...] = ()
    issues: tuple[GraphRow, ...] = ()
    pull_requests: tuple[GraphRow, ...] = ()
    commits: tuple[GraphRow, ...] = ()
    files: tuple[GraphRow, ...] = ()
    developers: tuple[GraphRow, ...] = ()
    repository_branches: tuple[GraphRow, ...] = ()
    repository_issues: tuple[GraphRow, ...] = ()
    repository_pull_requests: tuple[GraphRow, ...] = ()
    repository_commits: tuple[GraphRow, ...] = ()
    repository_files: tuple[GraphRow, ...] = ()
    branch_heads: tuple[GraphRow, ...] = ()
    pull_request_commits: tuple[GraphRow, ...] = ()
    pull_request_files: tuple[GraphRow, ...] = ()
    pull_request_resolutions: tuple[GraphRow, ...] = ()
    pull_request_references: tuple[GraphRow, ...] = ()
    commit_parents: tuple[GraphRow, ...] = ()
    commit_files: tuple[GraphRow, ...] = ()
    developer_issues: tuple[GraphRow, ...] = ()
    developer_pull_requests: tuple[GraphRow, ...] = ()
    developer_commits: tuple[GraphRow, ...] = ()
