"""Relational persistence model for messages in a chat session."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession


class ChatMessageRole(StrEnum):
    """Supported message authors in a persisted chat conversation."""

    USER = "user"
    ASSISTANT = "assistant"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatMessage(db.Model):
    """A user question or assistant answer belonging to one chat session."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_chat_messages_role",
        ),
        Index(
            "ix_chat_messages_session_id_created_at",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_answer: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
