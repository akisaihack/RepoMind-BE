"""Parse a local Java repository and persist its repository-scoped code graph."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.graph.mappings import map_java_file, resolve_cross_file_references
from app.graph.repositories.code_graph import CodeGraphRepository
from app.services.repository_identity import RepositoryIdentity, RepositoryIdentityValidator


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

        java_files = sorted(repository_path.rglob("*.java"))
        documents = []
        if java_files:
            from app.parsers.languages.java import parse_java_file

        for file_path in java_files:
            relative_path = file_path.relative_to(repository_path).as_posix()
            file_result = parse_java_file(relative_path, file_path.read_bytes())
            documents.append(map_java_file(github_repository_id, file_result, commit_hash))

        document = resolve_cross_file_references(documents)
        skipped_external = self._graph_repository.save(
            document,
            github_repository_id=github_repository_id,
            commit_hash=commit_hash,
        )

        counts = {node_type: 0 for node_type in _RESULT_NODE_TYPES}
        for node in document.nodes:
            if node.type in counts:
                counts[node.type] += 1

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
