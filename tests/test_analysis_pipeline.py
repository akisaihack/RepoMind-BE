from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.analysis_pipeline import AnalysisPipelineService


@pytest.fixture
def mocks():
    return {
        "git_clone": MagicMock(),
        "history_import": MagicMock(),
        "code_graph_import": MagicMock(),
        "chunk_import": MagicMock(),
        "repository_store": MagicMock(),
    }


@pytest.fixture
def service(mocks):
    return AnalysisPipelineService(
        git_clone_service=mocks["git_clone"],
        history_import_service=mocks["history_import"],
        code_graph_import_service=mocks["code_graph_import"],
        chunk_import_service=mocks["chunk_import"],
        repository_store=mocks["repository_store"],
    )


def test_run_pipeline_success(service, mocks):
    repo_id = uuid4()
    
    history_result = MagicMock()
    history_result.repository_id = 123
    mocks["history_import"].import_history.return_value = history_result
    
    mock_path = MagicMock()
    mocks["git_clone"].clone.return_value.__enter__.return_value = mock_path
    mocks["git_clone"].get_commit_hash.return_value = "fakehash"
    
    repo_mock = MagicMock()
    mocks["repository_store"].get.return_value = repo_mock

    service.run_pipeline(repo_id, "https://github.com/foo/bar", "main")
    
    # Check status transitions
    mocks["repository_store"].transition_status.assert_any_call(repo_id, "pending", "indexing")
    mocks["repository_store"].transition_status.assert_any_call(repo_id, "indexing", "ready")
    
    # Check method calls
    mocks["history_import"].import_history.assert_called_once()
    mocks["git_clone"].clone.assert_called_once_with("https://github.com/foo/bar", "main")
    mocks["code_graph_import"].import_repository.assert_called_once_with(
        github_repository_id=123,
        repository_path=mock_path,
    )
    mocks["chunk_import"].import_repository.assert_called_once_with(
        github_repository_id=123,
        repository_path=mock_path,
        commit_hash="fakehash",
    )
    
    # Check attributes updated
    assert repo_mock.github_repository_id == 123
    assert repo_mock.latest_analyzed_sha == "fakehash"


def test_run_pipeline_failure(service, mocks):
    repo_id = uuid4()
    
    mocks["history_import"].import_history.side_effect = ValueError("Some error")
    
    with pytest.raises(ValueError, match="Some error"):
        service.run_pipeline(repo_id, "https://github.com/foo/bar", "main")
        
    mocks["repository_store"].transition_status.assert_any_call(repo_id, "pending", "indexing")
    mocks["repository_store"].transition_status.assert_any_call(repo_id, "indexing", "failed")
