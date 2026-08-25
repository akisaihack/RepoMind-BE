"""Add MethodVersion history indexing checkpoint.

Revision ID: 20260825_01
Revises: 20260823_01
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_01"
down_revision: str | None = "20260823_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("history_indexed_sha", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repositories", "history_indexed_sha")
