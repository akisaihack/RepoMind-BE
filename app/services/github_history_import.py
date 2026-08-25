"""Orchestrate GitHub collection and persistence across PostgreSQL and Neo4j."""

from dataclasses import dataclass

from app.graph.mappers.github import GitHubGraphMapper
from app.graph.repositories.github_history import GitHubHistoryGraphRepository
from app.repositories.commit_file_change import CommitFileChangeRepository
from app.services.github_history import GitHubHistoryCollector


@dataclass(frozen=True, slots=True)
class GitHubHistoryImportResult:
    repository_id: int
    repository: str
    branches: int
    issues: int
    pull_requests: int
    commits: int
    file_changes: int


class GitHubHistoryImportService:
    def __init__(
        self,
        collector: GitHubHistoryCollector,
        file_change_repository: CommitFileChangeRepository,
        graph_mapper: GitHubGraphMapper,
        graph_repository: GitHubHistoryGraphRepository,
    ) -> None:
        self._collector = collector
        self._file_change_repository = file_change_repository
        self._graph_mapper = graph_mapper
        self._graph_repository = graph_repository

    def import_history(self, branch: str) -> GitHubHistoryImportResult:
        """Collect once, persist patches first, then write their IDs into the graph."""
        history = self._collector.collect(branch)
        file_change_ids = self._file_change_repository.upsert_changes(
            history.repository.id,
            history.commits,
        )
        graph_data = self._graph_mapper.map(history, file_change_ids)
        self._graph_repository.save(graph_data)

        return GitHubHistoryImportResult(
            repository_id=history.repository.id,
            repository=history.repository.full_name,
            branches=len(history.branches),
            issues=len(history.issues),
            pull_requests=len(history.pull_requests),
            commits=len(history.commits),
            file_changes=len(file_change_ids),
        )
