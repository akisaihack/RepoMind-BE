"""Create code_chunks.

Revision ID: 20260816_01
Revises: 20260811_01
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260816_01"
down_revision: str | None = "20260811_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Azure OpenAI 임베딩 배포(AZURE_OPENAI_EMBEDDING_DEPLOYMENT)가 1536차원 모델
# (예: text-embedding-3-small/ada-002 계열)이라고 가정하고 잡은 값. 실제
# 배포 모델과 다르면 이 컬럼 차원을 바꾸는 마이그레이션을 추가로 만들어야 함
# (아직 데이터가 없는 시점이라 지금 바꾸는 건 위험 부담이 적음).
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    # 로컬 docker는 docker/postgres/init.sql이 컨테이너 생성 시 자동으로
    # 켜주지만, 원격/공유 DB(team2db 등)는 아무도 켜준 적이 없을 수 있어서
    # 여기서 명시적으로 활성화함. 이미 켜져 있으면 IF NOT EXISTS라 안전함.
    # op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "code_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("graph_node_id", sa.Text(), nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("commit_hash", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("package", sa.Text(), nullable=True),
        sa.Column("class_name", sa.Text(), nullable=True),
        sa.Column("class_kind", sa.String(length=20), nullable=False),
        sa.Column("layer", sa.String(length=50), nullable=False),
        sa.Column("method_name", sa.Text(), nullable=True),
        sa.Column("param_signature", sa.Text(), nullable=False),
        sa.Column("is_constructor", sa.Boolean(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("api_http_method", sa.String(length=10), nullable=True),
        sa.Column("api_path", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
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
            "class_kind IN ('class', 'interface')",
            name="ck_code_chunks_class_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_node_id", name="uq_code_chunks_graph_node_id"),
    )
    op.create_index(
        "ix_code_chunks_github_repository_id",
        "code_chunks",
        ["github_repository_id"],
    )
    op.create_index(
        "ix_code_chunks_commit_hash",
        "code_chunks",
        ["commit_hash"],
    )
    # 코사인 유사도 기반 벡터 검색용 HNSW 인덱스. 임베딩 검색 쿼리(pgvector의
    # `<=>` 연산자)가 이 인덱스를 타야 대규모 데이터에서도 빠름.
    op.execute(
        "CREATE INDEX ix_code_chunks_embedding_hnsw ON code_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_code_chunks_embedding_hnsw")
    op.drop_index("ix_code_chunks_commit_hash", table_name="code_chunks")
    op.drop_index("ix_code_chunks_github_repository_id", table_name="code_chunks")
    op.drop_table("code_chunks")
