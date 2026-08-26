"""LLM-facing development history context models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HistoryVersionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    method_key: str
    path: str | None = None
    symbol: str
    source_code: str
    start_line: int
    end_line: int
    content_hash: str
    evidence_id: str | None = None


class HistoryCommitContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    sha: str
    message: str | None = None
    author: str | None = None
    authored_at: str | None = None
    committed_at: str | None = None
    url: str | None = None
    evidence_id: str | None = None


class HistoryPullRequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    number: int
    title: str
    body: str | None = None
    state: str | None = None
    url: str | None = None
    merged: bool | None = None
    merged_at: str | None = None
    evidence_id: str | None = None


class HistoryIssueContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    number: int
    title: str
    relation: Literal["RESOLVES", "REFERENCES"]
    body: str | None = None
    state: str | None = None
    url: str | None = None
    labels: list[str] = Field(default_factory=list)
    evidence_id: str | None = None


class HistoryDiffContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_commit_sha: str | None = None
    previous_content_hash: str | None = None
    added_lines: list[str] = Field(default_factory=list)
    removed_lines: list[str] = Field(default_factory=list)


class HistoryChangeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    change_type: Literal["first_observed", "modified", "deleted"]
    version: HistoryVersionContext | None = None
    commit: HistoryCommitContext
    diff: HistoryDiffContext | None = None
    pull_requests: list[HistoryPullRequestContext] = Field(default_factory=list)
    issues: list[HistoryIssueContext] = Field(default_factory=list)


__all__ = [
    "HistoryChangeContext",
    "HistoryCommitContext",
    "HistoryDiffContext",
    "HistoryIssueContext",
    "HistoryPullRequestContext",
    "HistoryVersionContext",
]
