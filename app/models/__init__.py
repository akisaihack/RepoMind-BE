"""SQLAlchemy model registration."""

from app.models.code_chunk import CodeChunk
from app.models.commit_file_change import CommitFileChange, CommitFileChangeHunk
from app.models.repository import Repository, RepositoryAnalysisStatus

__all__ = [
    "CodeChunk",
    "CommitFileChange",
    "CommitFileChangeHunk",
    "Repository",
    "RepositoryAnalysisStatus",
]


def register_models() -> None:
    """Import every model so migration metadata contains all tables."""
    _ = (CodeChunk, CommitFileChange, CommitFileChangeHunk, Repository)
