"""GitHub history import orchestration tests."""

from unittest.mock import Mock

from app.dtos.github import DevelopmentHistoryDTO, RepositoryDTO
from app.services.github_history_import import GitHubHistoryImportService


def test_persists_file_changes_before_mapping_and_graph_save() -> None:
    history = DevelopmentHistoryDTO(
        repository=RepositoryDTO(
            id=100,
            name="repo",
            full_name="org/repo",
            html_url="https://github.com/org/repo",
            default_branch="main",
            private=False,
            description=None,
        ),
        branches=(),
        issues=(),
        pull_requests=(),
        commits=(),
    )
    collector = Mock()
    collector.collect.return_value = history
    file_repository = Mock()
    file_repository.upsert_changes.return_value = {("abc123", "app.py"): 105}
    mapper = Mock()
    graph_data = Mock()
    mapper.map.return_value = graph_data
    graph_repository = Mock()

    result = GitHubHistoryImportService(
        collector,
        file_repository,
        mapper,
        graph_repository,
    ).import_history()

    file_repository.upsert_changes.assert_called_once_with(100, ())
    mapper.map.assert_called_once_with(history, {("abc123", "app.py"): 105})
    graph_repository.save.assert_called_once_with(graph_data)
    assert result.repository == "org/repo"
    assert result.file_changes == 1
