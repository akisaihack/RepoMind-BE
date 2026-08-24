"""Parse sources (Java/JavaScript/JSX) from a local checkout, embed chunks,
and persist to pgvector.

app/services/code_graph_import.py와 짝을 이루는 서비스 — 그래프 쪽이 Neo4j에
Method/MethodVersion 노드를 저장한다면, 이 서비스는 같은 소스에서 뽑은 청크를
임베딩해서 pgvector(code_chunks 테이블)에 저장함. graph_node_id가 동일한
content hash 공식으로 계산되기 때문에 정확한 MethodVersion과 연결됨.

지원 언어/확장자는 app/parsers/registry.py에 등록돼 있음.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from app.dtos.chunk import CodeChunk
from app.parsers.registry import discover_source_files, language_support_for
from app.repositories.code_chunk import CodeChunkRepository
from app.services.chunking import build_chunks_from_file
from app.services.embedding import EmbeddingService

DEFAULT_EMBEDDING_BATCH_SIZE = 100


@dataclass(frozen=True, slots=True)
class ChunkImportResult:
    github_repository_id: int
    commit_hash: str
    files: int
    chunks: int


class ChunkImportService:
    def __init__(
        self,
        chunk_repository: CodeChunkRepository,
        embedding_service: EmbeddingService,
        embedding_batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        if embedding_batch_size <= 0:
            raise ValueError("Embedding batch size must be positive.")
        self._chunk_repository = chunk_repository
        self._embedding_service = embedding_service
        self._embedding_batch_size = embedding_batch_size
        # 기본은 아무것도 출력하지 않는 no-op — CLI 스크립트가 print를 넘겨서
        # 진행 상황을 보여줌. 이게 없으면 47개 파일을 처리하는 동안 아무
        # 출력도 없어서 "멈췄나?" 싶은 상황이 생김.
        self._on_progress = on_progress or (lambda _message: None)

    def import_repository(
        self,
        github_repository_id: int,
        repository_path: Path,
        commit_hash: str,
    ) -> ChunkImportResult:
        """저장소 하나를 파싱 -> 청킹 -> 임베딩 -> pgvector 저장까지 실행.

        github_repository_id/commit_hash는 반드시 실제 값이어야 함 — 더미값을
        넣으면 code_chunks 행이 실제 Repository/Commit 그래프 노드와 연결되지
        않음(app/dtos/chunk.py 참고).
        """
        repository_path = repository_path.resolve()
        if not repository_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repository_path}")
        if not commit_hash.strip():
            raise ValueError("commit_hash must not be empty.")

        source_files = discover_source_files(repository_path)
        self._on_progress(f"parsing {len(source_files)} source files...")
        chunks: list[CodeChunk] = []
        for index, file_path in enumerate(source_files, start=1):
            support = language_support_for(file_path)
            if support is None:
                continue  # discover_source_files가 이미 걸러줌 — 방어적 스킵
            relative_path = file_path.relative_to(repository_path).as_posix()
            # CRLF -> LF 통일 (scripts/check_chunking.py와 동일한 이유).
            source_bytes = file_path.read_bytes().replace(b"\r\n", b"\n")
            file_result = support.parse(relative_path, source_bytes)
            file_chunks = build_chunks_from_file(github_repository_id, file_result, commit_hash)
            chunks.extend(file_chunks)
            self._on_progress(
                f"[{index}/{len(source_files)}] {relative_path}: {len(file_chunks)} chunks"
            )

        existing_ids = self._chunk_repository.find_existing_graph_node_ids(
            [chunk.graph_node_id for chunk in chunks]
        )
        new_chunks = [chunk for chunk in chunks if chunk.graph_node_id not in existing_ids]
        if existing_ids:
            self._on_progress(f"reusing {len(existing_ids)} existing version chunks.")

        if new_chunks:
            self._on_progress(f"embedding {len(new_chunks)} new version chunks via Azure OpenAI...")
            embeddings = self._embed_all(chunk.text for chunk in new_chunks)
            self._on_progress("writing chunks + embeddings to pgvector...")
            self._chunk_repository.upsert_chunks(new_chunks, embeddings)
            self._on_progress("pgvector write complete.")
        else:
            self._on_progress("no new code versions found, nothing to embed.")

        return ChunkImportResult(
            github_repository_id=github_repository_id,
            commit_hash=commit_hash,
            files=len(source_files),
            chunks=len(chunks),
        )

    def _embed_all(self, texts: Iterable[str]) -> list[list[float]]:
        """Azure OpenAI 요청 크기 제한을 피하려고 배치 단위로 나눠서 임베딩."""
        text_list = list(texts)
        embeddings: list[list[float]] = []
        batch_count = (
            len(text_list) + self._embedding_batch_size - 1
        ) // self._embedding_batch_size
        starts = range(0, len(text_list), self._embedding_batch_size)
        for batch_index, start in enumerate(starts, 1):
            batch = text_list[start : start + self._embedding_batch_size]
            self._on_progress(f"  embedding batch {batch_index}/{batch_count} ({len(batch)} texts)")
            embeddings.extend(self._embedding_service.embed(batch))
        return embeddings
