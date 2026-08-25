"""Parse a local repository (Java/JavaScript/JSX) and persist its
repository-scoped code graph.

지원 언어/확장자는 app/parsers/registry.py에 등록돼 있음 — 새 언어를 추가할
때 이 파일은 손댈 필요 없음(레지스트리를 통해서만 파서/매퍼를 찾음).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.dtos.graph import GraphDocument
from app.graph.mappings import resolve_cross_file_references
from app.graph.repositories.code_graph import CodeGraphRepository
from app.parsers.registry import discover_source_files, language_support_for
from app.services.repository_identity import RepositoryIdentity, RepositoryIdentityValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CodeGraphImportResult:
    github_repository_id: int
    commit_hash: str
    files: int
    packages: int
    classes: int
    interfaces: int
    methods: int
    endpoints: int
    relationships: int
    skipped_external_relationships: int
    repository_full_name: str | None
    repository_validation_source: str
    repository_validation_skipped: bool


class CodeGraphImportService:
    def __init__(
        self,
        graph_repository: CodeGraphRepository,
        identity_validator: RepositoryIdentityValidator,
        on_identity_validated: Callable[[RepositoryIdentity], None] | None = None,
    ) -> None:
        self._graph_repository = graph_repository
        self._identity_validator = identity_validator
        self._on_identity_validated = on_identity_validated

    def import_repository(
        self,
        github_repository_id: int,
        repository_path: Path,
        commit_hash: str,
        *,
        skip_repository_validation: bool = False,
        persist_version_history: bool = True,
        mark_missing_deleted: bool = True,
    ) -> CodeGraphImportResult:
        repository_path = repository_path.resolve()
        if not repository_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repository_path}")
        if not commit_hash.strip():
            raise ValueError("commit_hash must not be empty.")

        identity = self._identity_validator.validate(
            github_repository_id,
            repository_path,
            skip=skip_repository_validation,
        )
        if self._on_identity_validated is not None:
            self._on_identity_validated(identity)

        source_files = discover_source_files(repository_path)
        logger.info("최신 소스 파일 파싱을 시작합니다. 전체=%s개", len(source_files))
        documents = []
        for index, file_path in enumerate(source_files, start=1):
            support = language_support_for(file_path)
            if support is None:
                # discover_source_files가 이미 지원 확장자만 걸러서 주기
                # 때문에 이론상 발생하지 않지만, 방어적으로 건너뜀.
                continue
            relative_path = file_path.relative_to(repository_path).as_posix()
            file_result = support.parse(relative_path, file_path.read_bytes())
            documents.append(support.map_to_graph(github_repository_id, file_result, commit_hash))
            if index == 1 or index == len(source_files) or index % 25 == 0:
                logger.info(
                    "최신 소스 파일 파싱 진행률=%s/%s, 파일=%s",
                    index,
                    len(source_files),
                    relative_path,
                )

        logger.info("파일 간 코드 참조 관계를 연결합니다. 파일=%s개", len(documents))
        document = resolve_cross_file_references(documents)
        if not persist_version_history:
            document = GraphDocument(
                nodes=document.nodes,
                edges=tuple(
                    edge for edge in document.edges if edge.type != "INTRODUCED_IN"
                ),
            )
        logger.info(
            "최신 코드 그래프를 Neo4j에 저장합니다. 노드=%s개, 관계=%s개",
            len(document.nodes),
            len(document.edges),
        )
        skipped_external = self._graph_repository.save(
            document,
            github_repository_id=github_repository_id,
            commit_hash=commit_hash,
            mark_missing_deleted=mark_missing_deleted,
        )

        counts = {node_type: 0 for node_type in _RESULT_NODE_TYPES}
        for node in document.nodes:
            if node.type in counts:
                counts[node.type] += 1

        logger.info(
            "최신 코드 그래프 저장을 완료했습니다. 파일=%s개, 메서드=%s개, "
            "관계=%s개, 제외된 외부 관계=%s개",
            counts["File"],
            counts["Method"],
            len(document.edges) - skipped_external,
            skipped_external,
        )

        return CodeGraphImportResult(
            github_repository_id=github_repository_id,
            commit_hash=commit_hash,
            files=counts["File"],
            packages=counts["Package"],
            classes=counts["Class"],
            interfaces=counts["Interface"],
            methods=counts["Method"],
            endpoints=counts["Endpoint"],
            relationships=len(document.edges) - skipped_external,
            skipped_external_relationships=skipped_external,
            repository_full_name=identity.expected_full_name,
            repository_validation_source=identity.source,
            repository_validation_skipped=identity.skipped,
        )


_RESULT_NODE_TYPES = ("File", "Package", "Class", "Interface", "Method", "Endpoint")
