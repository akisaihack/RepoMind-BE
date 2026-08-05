"""Create Commit file changes and patch hunks.

Revision ID: 20260804_01
Revises:
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commit_file_changes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("previous_file_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=False),
        sa.Column("deletions", sa.Integer(), nullable=False),
        sa.Column("changes", sa.Integer(), nullable=False),
        sa.Column("patch", sa.Text(), nullable=True),
        sa.Column("patch_source", sa.String(length=20), nullable=False),
        sa.Column("patch_status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "patch_status IN ('available', 'unavailable')",
            name="ck_commit_file_changes_patch_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "github_repository_id",
            "commit_sha",
            "file_path",
            name="uq_commit_file_changes_repository_commit_path",
        ),
    )
    op.create_index(
        "ix_commit_file_changes_github_repository_id",
        "commit_file_changes",
        ["github_repository_id"],
    )
    op.create_index(
        "ix_commit_file_changes_commit_sha",
        "commit_file_changes",
        ["commit_sha"],
    )
    op.create_table(
        "commit_file_change_hunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_change_id", sa.BigInteger(), nullable=False),
        sa.Column("old_start_line", sa.Integer(), nullable=False),
        sa.Column("old_line_count", sa.Integer(), nullable=False),
        sa.Column("new_start_line", sa.Integer(), nullable=False),
        sa.Column("new_line_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_change_id"],
            ["commit_file_changes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commit_file_change_hunks_file_change_id",
        "commit_file_change_hunks",
        ["file_change_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commit_file_change_hunks_file_change_id",
        table_name="commit_file_change_hunks",
    )
    op.drop_table("commit_file_change_hunks")
    op.drop_index("ix_commit_file_changes_commit_sha", table_name="commit_file_changes")
    op.drop_index(
        "ix_commit_file_changes_github_repository_id",
        table_name="commit_file_changes",
    )
    op.drop_table("commit_file_changes")
