"""Parse Java sources from a local checkout, embed chunks, and persist to pgvector."""

import argparse
from pathlib import Path

from app import create_app
from app.clients.azure_openai import create_azure_openai_client
from app.errors import APIError
from app.extensions import db
from app.repositories.code_chunk import ChunkPersistenceError, CodeChunkRepository
from app.services.chunk_import import DEFAULT_EMBEDDING_BATCH_SIZE, ChunkImportService
from app.services.embedding import EmbeddingService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument("--repository-path", required=True, type=Path)
    parser.add_argument(
        "--commit-hash",
        required=True,
        help="이 코드 스냅샷이 해당하는 실제 커밋 SHA (더미값 금지).",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=DEFAULT_EMBEDDING_BATCH_SIZE,
        help="한 번의 Azure OpenAI 요청에 담을 청크 텍스트 개수.",
    )
    args = parser.parse_args()

    app = create_app()
    try:
        with app.app_context():
            deployment = app.config.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
            if not deployment:
                raise SystemExit("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is not configured.")

            azure_client = create_azure_openai_client(app.config)
            embedding_service = EmbeddingService(azure_client, deployment)
            chunk_repository = CodeChunkRepository(db.session)

            result = ChunkImportService(
                chunk_repository,
                embedding_service,
                embedding_batch_size=args.embedding_batch_size,
                on_progress=lambda message: print(message, flush=True),
            ).import_repository(
                args.github_repository_id,
                args.repository_path,
                args.commit_hash,
            )
    except (APIError, ChunkPersistenceError, OSError, ValueError) as exc:
        # ChunkPersistenceError 등은 원래 SQLAlchemy 에러를 감싸서 던지는데,
        # SystemExit는 기본적으로 원인(cause)을 화면에 안 보여줘서 진짜 원인이
        # 감춰짐. __cause__를 직접 붙여서 실제 DB 에러 메시지가 보이게 함.
        cause = exc.__cause__
        detail = f"\ncause: {cause!r}" if cause is not None else ""
        raise SystemExit(f"Chunk import failed: {exc}{detail}") from exc

    print("Chunk import: OK")
    for field in result.__dataclass_fields__:
        print(f"{field}={getattr(result, field)}")


if __name__ == "__main__":
    main()
