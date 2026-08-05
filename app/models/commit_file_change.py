"""Relational persistence for Commit-level file patches and diff hunks."""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

_PRIMARY_KEY_TYPE = BigInteger().with_variant(Integer, "sqlite")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CommitFileChange(db.Model):
    __tablename__ = "commit_file_changes"
    __table_args__ = (
        UniqueConstraint(
            "github_repository_id",
            "commit_sha",
            "file_path",
            name="uq_commit_file_changes_repository_commit_path",
        ),
        CheckConstraint(
            "patch_status IN ('available', 'unavailable')",
            name="ck_commit_file_changes_patch_status",
        ),
    )

    id: Mapped[int] = mapped_column(_PRIMARY_KEY_TYPE, primary_key=True, autoincrement=True)
    github_repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    previous_file_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patch: Mapped[str | None] = mapped_column(Text)
    patch_source: Mapped[str] = mapped_column(String(20), nullable=False, default="github")
    patch_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow, onupdate=_utcnow)

    hunks: Mapped[list["CommitFileChangeHunk"]] = relationship(
        back_populates="file_change",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CommitFileChangeHunk(db.Model):
    __tablename__ = "commit_file_change_hunks"

    id: Mapped[int] = mapped_column(_PRIMARY_KEY_TYPE, primary_key=True, autoincrement=True)
    file_change_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("commit_file_changes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    old_line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    new_line_count: Mapped[int] = mapped_column(Integer, nullable=False)

    file_change: Mapped[CommitFileChange] = relationship(back_populates="hunks")
