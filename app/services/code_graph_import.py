"""Parse a local Java repository and persist its repository-scoped code graph."""

from dataclasses import dataclass
from pathlib import Path

from app.graph.mappings import map_java_file, resolve_cross_file_references
from app.graph.repositories.code_graph import CodeGraphRepository
from app.parsers.languages.java import parse_java_file


@dataclass(frozen=True, slots=True)
class CodeGraphImportResult:
    github_repository_id: int
    files: int
    packages: int
    classes: int
    interfaces: int
    methods: int
    endpoints: int
    relationships: int
    skipped_external_relationships: int


class CodeGraphImportService:
    def __init__(self, graph_repository: CodeGraphRepository) -> None:
        self._graph_repository = graph_repository

    def import_repository(
        self, github_repository_id: int, repository_path: Path
    ) -> CodeGraphImportResult:
        repository_path = repository_path.resolve()
        if not repository_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repository_path}")

        java_files = sorted(repository_path.rglob("*.java"))
        documents = []
        for file_path in java_files:
            relative_path = file_path.relative_to(repository_path).as_posix()
            file_result = parse_java_file(relative_path, file_path.read_bytes())
            documents.append(map_java_file(github_repository_id, file_result))

        document = resolve_cross_file_references(documents)
        skipped_external = self._graph_repository.save(document)

        counts = {node_type: 0 for node_type in _RESULT_NODE_TYPES}
        for node in document.nodes:
            if node.type in counts:
                counts[node.type] += 1

        return CodeGraphImportResult(
            github_repository_id=github_repository_id,
            files=counts["File"],
            packages=counts["Package"],
            classes=counts["Class"],
            interfaces=counts["Interface"],
            methods=counts["Method"],
            endpoints=counts["Endpoint"],
            relationships=len(document.edges) - skipped_external,
            skipped_external_relationships=skipped_external,
        )


_RESULT_NODE_TYPES = ("File", "Package", "Class", "Interface", "Method", "Endpoint")
