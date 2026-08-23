"""Relational persistence model for repository-scoped chat sessions."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage
    from app.models.repository import Repository


DEFAULT_CHAT_SESSION_TITLE = "새 대화"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatSession(db.Model):
    """A conversation that belongs to exactly one registered repository."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index(
            "ix_chat_sessions_repository_id_updated_at",
            "repository_id",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=DEFAULT_CHAT_SESSION_TITLE,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    repository: Mapped["Repository"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
