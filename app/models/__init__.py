"""SQLAlchemy model registration."""

from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import ChatSession
from app.models.code_chunk import CodeChunk
from app.models.commit_file_change import CommitFileChange, CommitFileChangeHunk
from app.models.repository import Repository, RepositoryAnalysisStatus

__all__ = [
    "ChatMessage",
    "ChatMessageRole",
    "ChatSession",
    "CodeChunk",
    "CommitFileChange",
    "CommitFileChangeHunk",
    "Repository",
    "RepositoryAnalysisStatus",
]


def register_models() -> None:
    """Import every model so migration metadata contains all tables."""
    _ = (
        ChatMessage,
        ChatSession,
        CodeChunk,
        CommitFileChange,
        CommitFileChangeHunk,
        Repository,
    )
