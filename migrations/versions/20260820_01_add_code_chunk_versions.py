"""Add logical Method and content version identifiers to code chunks.

Revision ID: 20260820_01
Revises: 20260816_01
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_01"
down_revision: str | None = "20260816_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("code_chunks", sa.Column("method_node_id", sa.Text(), nullable=True))
    op.add_column("code_chunks", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.execute("UPDATE code_chunks SET method_node_id = graph_node_id")
    op.execute("UPDATE code_chunks SET content_hash = repeat('0', 64)")
    op.alter_column("code_chunks", "method_node_id", nullable=False)
    op.alter_column("code_chunks", "content_hash", nullable=False)
    op.create_index(
        "ix_code_chunks_method_node_id", "code_chunks", ["method_node_id"]
    )
    op.create_index("ix_code_chunks_content_hash", "code_chunks", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_code_chunks_content_hash", table_name="code_chunks")
    op.drop_index("ix_code_chunks_method_node_id", table_name="code_chunks")
    op.drop_column("code_chunks", "content_hash")
    op.drop_column("code_chunks", "method_node_id")
