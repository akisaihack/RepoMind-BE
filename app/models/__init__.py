"""SQLAlchemy model registration."""

from app.models.commit_file_change import CommitFileChange, CommitFileChangeHunk

__all__ = ["CommitFileChange", "CommitFileChangeHunk"]


def register_models() -> None:
    """Import every model so migration metadata contains all tables."""
    _ = (CommitFileChange, CommitFileChangeHunk)
