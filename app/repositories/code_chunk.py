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
        """Upsert content-addressed MethodVersion chunks by graph_node_id."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        try:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                row = self._find(chunk.graph_node_id)
                if row is None:
                    row = self._find_legacy(chunk.method_node_id)
                    if row is None:
                        row = CodeChunk(graph_node_id=chunk.graph_node_id)
                        self._session.add(row)
                    else:
                        row.graph_node_id = chunk.graph_node_id

                row.chunk_id = chunk.id
                row.method_node_id = chunk.method_node_id
                row.content_hash = chunk.content_hash
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

    def find_existing_graph_node_ids(self, graph_node_ids: list[str]) -> set[str]:
        """Return MethodVersion chunk IDs that already have an embedding."""
        if not graph_node_ids:
            return set()
        statement = select(CodeChunk.graph_node_id).where(
            CodeChunk.graph_node_id.in_(graph_node_ids)
        )
        return set(self._session.scalars(statement).all())

    def _find(self, graph_node_id: str) -> CodeChunk | None:
        statement = select(CodeChunk).where(CodeChunk.graph_node_id == graph_node_id)
        return self._session.scalars(statement).one_or_none()

    def _find_legacy(self, method_node_id: str) -> CodeChunk | None:
        statement = select(CodeChunk).where(
            CodeChunk.method_node_id == method_node_id,
            CodeChunk.content_hash == "0" * 64,
        )
        return self._session.scalars(statement).one_or_none()
