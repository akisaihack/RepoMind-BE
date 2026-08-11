"""Create repositories.

Revision ID: 20260811_01
Revises: 20260804_01
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_01"
down_revision: str | None = "20260804_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_url", sa.Text(), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=True),
        sa.Column("latest_analyzed_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "analysis_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
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
            "analysis_status IN ('pending', 'indexing', 'ready', 'failed')",
            name="ck_repositories_analysis_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_repository_id", name="uq_repositories_github_repository_id"),
        sa.UniqueConstraint("repository_url", "branch", name="uq_repositories_url_branch"),
    )
def downgrade() -> None:
    op.drop_table("repositories")
