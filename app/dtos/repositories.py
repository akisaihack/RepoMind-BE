"""Data Transfer Objects for Repository Management API."""

from dataclasses import dataclass
from typing import Literal

RepositoryAnalysisStatus = Literal["pending", "indexing", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class RepositoryCreateRequest:
    """Request data required to register a source repository."""

    repository_url: str
    branch: str = "main"


@dataclass(frozen=True, slots=True)
class RepositoryInfo:
    """Registered repository data shared with the frontend."""

    id: str
    repository_url: str
    branch: str
    analysis_status: RepositoryAnalysisStatus
    latest_analyzed_sha: str | None


@dataclass(frozen=True, slots=True)
class RepositoryListResponse:
    """List response for registered repositories."""

    repositories: list[RepositoryInfo]


@dataclass(frozen=True, slots=True)
class RepositoryStatusResponse:
    """Analysis state for one registered repository."""

    id: str
    analysis_status: RepositoryAnalysisStatus
    latest_analyzed_sha: str | None
