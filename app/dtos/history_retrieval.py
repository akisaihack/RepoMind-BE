"""Neo4j 개발 이력 노드에서 보존할 내부 메타데이터 DTO."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MethodVersionHistoryMetadata(BaseModel):
    """특정 메서드 버전의 코드 스냅샷 정보."""

    model_config = ConfigDict(extra="forbid")

    node_type: Literal["MethodVersion"] = "MethodVersion"
    method_key: str
    source_code: str
    start_line: int
    end_line: int
    content_hash: str
    api_http_method: str | None = None
    api_path: str | None = None


class CommitHistoryMetadata(BaseModel):
    """MethodVersion과 연결된 Git 커밋 정보."""

    model_config = ConfigDict(extra="forbid")

    node_type: Literal["Commit"] = "Commit"
    sha: str
    message: str | None = None
    author: str | None = None
    authored_at: str | None = None
    committed_at: str | None = None
    url: str | None = None


class PullRequestHistoryMetadata(BaseModel):
    """Commit을 포함하는 GitHub Pull Request 정보."""

    model_config = ConfigDict(extra="forbid")

    node_type: Literal["PullRequest"] = "PullRequest"
    number: int
    title: str
    body: str | None = None
    state: str | None = None
    url: str | None = None
    merged: bool | None = None
    merged_at: str | None = None


class IssueHistoryMetadata(BaseModel):
    """Pull Request가 해결하거나 참조하는 GitHub Issue 정보."""

    model_config = ConfigDict(extra="forbid")

    node_type: Literal["Issue"] = "Issue"
    number: int
    title: str
    body: str | None = None
    state: str | None = None
    url: str | None = None
    labels: list[str] = Field(default_factory=list)


__all__ = [
    "CommitHistoryMetadata",
    "IssueHistoryMetadata",
    "MethodVersionHistoryMetadata",
    "PullRequestHistoryMetadata",
]
