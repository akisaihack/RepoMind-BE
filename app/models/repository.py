"""Repository registration persistence model."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession


class RepositoryAnalysisStatus(StrEnum):
    """Lifecycle states shared by the API and future analysis jobs."""

    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Repository(db.Model):
    """A registered source repository and its latest analysis state."""

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint(
            "repository_url",
            "branch",
            name="uq_repositories_url_branch",
        ),
        CheckConstraint(
            "analysis_status IN ('pending', 'indexing', 'ready', 'failed')",
            name="ck_repositories_analysis_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    repository_url: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    github_repository_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        unique=True,
    )
    latest_analyzed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    history_indexed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RepositoryAnalysisStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
