"""Index MethodVersion history from a branch's first-parent Git history."""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.dtos.graph import GraphDocument, GraphEdge, GraphNode
from app.graph.mappings import resolve_cross_file_references
from app.graph.repositories.code_graph import CodeGraphRepository
from app.parsers.registry import language_support_for
from app.services.git_clone import GitCloneService, GitCommit, GitFileChange

logger = logging.getLogger(__name__)

DEFAULT_MAX_COMMITS = 2_000
DEFAULT_MAX_CHANGED_FILES = 500


@dataclass(frozen=True, slots=True)
class MethodHistoryIndexResult:
    commits: int
    changed_files: int
    versions: int
    deletions: int
    last_commit_sha: str | None


class MethodHistoryLimitError(RuntimeError):
    """Raised when one commit exceeds the configured changed-file limit."""


class MethodHistoryIndexer:
    """Create historical MethodVersions without replacing the current snapshot graph."""

    def __init__(
        self,
        git: GitCloneService,
        graph_repository: CodeGraphRepository,
        *,
        max_commits: int = DEFAULT_MAX_COMMITS,
        max_changed_files: int = DEFAULT_MAX_CHANGED_FILES,
    ) -> None:
        self._git = git
        self._graph_repository = graph_repository
        self._max_commits = max_commits
        self._max_changed_files = max_changed_files

    def index(
        self,
        github_repository_id: int,
        repository_path: Path,
        *,
        after_sha: str | None = None,
    ) -> MethodHistoryIndexResult:
        commits = self._git.list_first_parent_commits(
            repository_path,
            after_sha=after_sha,
            max_commits=self._max_commits,
        )
        file_methods: dict[str, dict[str, GraphNode]] = {}
        previous_versions: dict[str, GraphNode] = {}
        if after_sha is not None:
            self._load_baseline(
                github_repository_id,
                repository_path,
                after_sha,
                file_methods,
                previous_versions,
            )

        changed_file_count = version_count = deletion_count = 0
        for position, commit in enumerate(commits, start=1):
            changes = self._supported_changes(
                self._git.list_changed_files(repository_path, commit)
            )
            if len(changes) > self._max_changed_files:
                raise MethodHistoryLimitError(
                    f"Commit {commit.sha} changes more than "
                    f"{self._max_changed_files} supported files."
                )
            changed_file_count += len(changes)
            documents: list[GraphDocument] = [
                _commit_document(github_repository_id, commit)
            ]
            deleted_method_keys: set[str] = set()

            for change in changes:
                old_path = change.previous_path or change.path
                old_methods = file_methods.pop(old_path, {})
                if change.status == "D":
                    deleted_method_keys.update(old_methods)
                    continue

                document = self._parse_file(
                    github_repository_id,
                    repository_path,
                    commit.sha,
                    change.path,
                )
                current_methods = _method_versions(document)
                deleted_method_keys.update(set(old_methods) - set(current_methods))
                file_methods[change.path] = current_methods
                introduced_version_ids = {
                    version.id
                    for method_key, version in current_methods.items()
                    if method_key not in old_methods
                    or old_methods[method_key].id != version.id
                }
                documents.append(
                    _with_version_ancestry(
                        document,
                        current_methods,
                        previous_versions,
                        introduced_version_ids,
                    )
                )
                for method_key, version in current_methods.items():
                    if previous_versions.get(method_key, version).id != version.id:
                        version_count += 1
                    elif method_key not in previous_versions:
                        version_count += 1
                    previous_versions[method_key] = version

            if documents:
                document = resolve_cross_file_references(documents)
                self._graph_repository.save(
                    document,
                    github_repository_id=github_repository_id,
                    commit_hash=commit.sha,
                    mark_missing_deleted=False,
                    resolve_introduction_history=False,
                )
            self._graph_repository.mark_methods_deleted(
                github_repository_id,
                commit.sha,
                sorted(deleted_method_keys),
            )
            deletion_count += len(deleted_method_keys)
            logger.info(
                "메서드 이력 인덱싱 진행률=%s/%s, 커밋=%s, 변경 파일=%s개, "
                "누적 버전=%s개, 누적 삭제=%s개",
                position,
                len(commits),
                commit.sha,
                len(changes),
                version_count,
                deletion_count,
            )

        return MethodHistoryIndexResult(
            commits=len(commits),
            changed_files=changed_file_count,
            versions=version_count,
            deletions=deletion_count,
            last_commit_sha=commits[-1].sha if commits else after_sha,
        )

    def _load_baseline(
        self,
        github_repository_id: int,
        repository_path: Path,
        commit_sha: str,
        file_methods: dict[str, dict[str, GraphNode]],
        previous_versions: dict[str, GraphNode],
    ) -> None:
        for path in self._git.list_files_at_commit(repository_path, commit_sha):
            if language_support_for(Path(path)) is None:
                continue
            document = self._parse_file(
                github_repository_id, repository_path, commit_sha, path
            )
            methods = _method_versions(document)
            file_methods[path] = methods
            previous_versions.update(methods)

    def _parse_file(
        self,
        github_repository_id: int,
        repository_path: Path,
        commit_sha: str,
        path: str,
    ) -> GraphDocument:
        support = language_support_for(Path(path))
        if support is None:
            raise ValueError(f"Unsupported source file: {path}")
        content = self._git.read_file_at_commit(repository_path, commit_sha, path)
        parsed = support.parse(path, content)
        return support.map_to_graph(github_repository_id, parsed, commit_sha)

    @staticmethod
    def _supported_changes(changes: list[GitFileChange]) -> list[GitFileChange]:
        return [
            change
            for change in changes
            if language_support_for(Path(change.path)) is not None
            or (
                change.previous_path is not None
                and language_support_for(Path(change.previous_path)) is not None
            )
        ]


def _method_versions(document: GraphDocument) -> dict[str, GraphNode]:
    versions = {node.id: node for node in document.nodes if node.type == "MethodVersion"}
    return {
        edge.source: versions[edge.target]
        for edge in document.edges
        if edge.type == "HAS_VERSION" and edge.target in versions
    }


def _commit_document(github_repository_id: int, commit: GitCommit) -> GraphDocument:
    commit_key = f"{github_repository_id}:commit:{commit.sha}"
    nodes = [
        GraphNode(
            commit_key,
            "Commit",
            {"sha": commit.sha, "githubRepositoryId": github_repository_id},
        )
    ]
    edges: list[GraphEdge] = []
    if commit.parent_sha is not None:
        parent_key = f"{github_repository_id}:commit:{commit.parent_sha}"
        nodes.append(
            GraphNode(
                parent_key,
                "Commit",
                {
                    "sha": commit.parent_sha,
                    "githubRepositoryId": github_repository_id,
                },
            )
        )
        edges.append(GraphEdge("PARENT", commit_key, parent_key, {}))
    return GraphDocument(tuple(nodes), tuple(edges))


def _with_version_ancestry(
    document: GraphDocument,
    current: dict[str, GraphNode],
    previous: dict[str, GraphNode],
    introduced_version_ids: set[str],
) -> GraphDocument:
    nodes = list(document.nodes)
    edges = [
        edge
        for edge in document.edges
        if edge.type != "INTRODUCED_IN" or edge.source in introduced_version_ids
    ]
    node_ids = {node.id for node in nodes}
    for method_key, current_version in current.items():
        previous_version = previous.get(method_key)
        if previous_version is None or previous_version.id == current_version.id:
            continue
        if previous_version.id not in node_ids:
            nodes.append(previous_version)
            node_ids.add(previous_version.id)
        edges.append(
            GraphEdge(
                type="DERIVED_FROM",
                source=current_version.id,
                target=previous_version.id,
                properties={},
            )
        )
    return GraphDocument(tuple(nodes), tuple(edges))


__all__ = [
    "MethodHistoryIndexer",
    "MethodHistoryIndexResult",
    "MethodHistoryLimitError",
]
