"""Relational + vector persistence for pgvector code chunks."""

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

_PRIMARY_KEY_TYPE = BigInteger().with_variant(Integer, "sqlite")

# app/dtos/chunk.py 쪽과 반드시 맞춰야 함 — 다르면 임베딩 저장 시 차원 오류.
EMBEDDING_DIMENSIONS = 1536


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CodeChunk(db.Model):
    """메서드/생성자 단위 코드 청크 + 임베딩 벡터.

    graph_node_id가 Neo4j Method 노드 id와 항상 동일하므로(app/graph/
    mappings.py 공식 재사용, app/services/chunking.py 참고), 이 컬럼을
    기준으로 pgvector 검색 결과를 그래프 노드로 바로 연결할 수 있음.

    한 메서드당 최신 스냅샷 한 행만 유지함(graph_node_id UNIQUE) — 재분석
    시 새 커밋 값으로 upsert(덮어쓰기)하며, 커밋별 이력을 계속 쌓지 않음.
    """

    __tablename__ = "code_chunks"
    __table_args__ = (
        CheckConstraint(
            "class_kind IN ('class', 'interface')",
            name="ck_code_chunks_class_kind",
        ),
        UniqueConstraint("graph_node_id", name="uq_code_chunks_graph_node_id"),
    )

    id: Mapped[int] = mapped_column(_PRIMARY_KEY_TYPE, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(Text, nullable=False)
    graph_node_id: Mapped[str] = mapped_column(Text, nullable=False)
    github_repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    commit_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    package: Mapped[str | None] = mapped_column(Text)
    class_name: Mapped[str | None] = mapped_column(Text)
    class_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    layer: Mapped[str] = mapped_column(String(50), nullable=False)
    method_name: Mapped[str | None] = mapped_column(Text)
    param_signature: Mapped[str] = mapped_column(Text, nullable=False)
    is_constructor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    api_http_method: Mapped[str | None] = mapped_column(String(10))
    api_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=_utcnow, onupdate=_utcnow
    )
