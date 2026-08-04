"""DTOs for normalized GitHub development history."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepositoryDTO:
    id: int
    name: str
    full_name: str
    html_url: str
    default_branch: str
    private: bool
    description: str | None


@dataclass(frozen=True, slots=True)
class BranchDTO:
    name: str
    sha: str
    protected: bool


@dataclass(frozen=True, slots=True)
class IssueDTO:
    number: int
    title: str
    state: str
    body: str | None
    author: str | None
    html_url: str
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class CommitFileDTO:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    blob_url: str | None
    raw_url: str | None
    patch: str | None


@dataclass(frozen=True, slots=True)
class CommitDTO:
    sha: str
    message: str
    html_url: str
    author_name: str | None
    author_login: str | None
    authored_at: str | None
    committed_at: str | None
    parent_shas: tuple[str, ...]
    files: tuple[CommitFileDTO, ...]


@dataclass(frozen=True, slots=True)
class PullRequestDTO:
    number: int
    title: str
    state: str
    body: str | None
    author: str | None
    html_url: str
    base_branch: str
    head_branch: str
    head_sha: str
    merge_commit_sha: str | None
    merged: bool
    created_at: str
    updated_at: str
    closed_at: str | None
    merged_at: str | None
    commit_shas: tuple[str, ...]
    files: tuple[CommitFileDTO, ...]


@dataclass(frozen=True, slots=True)
class DevelopmentHistoryDTO:
    repository: RepositoryDTO
    branches: tuple[BranchDTO, ...]
    issues: tuple[IssueDTO, ...]
    pull_requests: tuple[PullRequestDTO, ...]
    commits: tuple[CommitDTO, ...]
