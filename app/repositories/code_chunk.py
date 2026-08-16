"""PostgreSQL persistence for code chunks and their embedding vectors.

임베딩 호출(Azure OpenAI API)은 여기서 하지 않음 — 그건 app/services/
chunk_import.py 책임. 이 클래스는 이미 계산된 (CodeChunk, embedding) 쌍을
graph_node_id 기준으로 DB에 쓰는 것만 담당함 (app/repositories/
commit_file_change.py와 동일한 책임 분리 패턴).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.dtos.chunk import CodeChunk as CodeChunkDTO
from app.models.code_chunk import CodeChunk


class ChunkPersistenceError(Exception):
    """Raised when code chunk persistence fails."""


class CodeChunkRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_chunks(
        self,
        chunks: list[CodeChunkDTO],
        embeddings: list[list[float]],
    ) -> int:
        """chunk/embedding 쌍을 graph_node_id 기준으로 upsert.

        같은 메서드를 다시 분석하면(재실행) 기존 행을 최신 커밋 값으로
        덮어씀 — 커밋별 이력을 계속 쌓는 게 아니라 최신 스냅샷 하나만 유지.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        try:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                row = self._find(chunk.graph_node_id)
                if row is None:
                    row = CodeChunk(graph_node_id=chunk.graph_node_id)
                    self._session.add(row)

                row.chunk_id = chunk.id
                row.github_repository_id = chunk.github_repository_id
                row.commit_hash = chunk.commit_hash
                row.path = chunk.path
                row.package = chunk.package
                row.class_name = chunk.class_name
                row.class_kind = chunk.class_kind
                row.layer = chunk.layer
                row.method_name = chunk.method_name
                row.param_signature = chunk.param_signature
                row.is_constructor = chunk.is_constructor
                row.start_line = chunk.start_line
                row.end_line = chunk.end_line
                row.api_http_method = (
                    chunk.api_mapping.http_method if chunk.api_mapping else None
                )
                row.api_path = chunk.api_mapping.path if chunk.api_mapping else None
                row.text = chunk.text
                row.embedding = embedding
                row.updated_at = datetime.now(UTC)
                self._session.flush()

            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChunkPersistenceError("Failed to persist code chunks.") from exc

        return len(chunks)

    def _find(self, graph_node_id: str) -> CodeChunk | None:
        statement = select(CodeChunk).where(CodeChunk.graph_node_id == graph_node_id)
        return self._session.scalars(statement).one_or_none()
