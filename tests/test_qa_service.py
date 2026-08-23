"""Tests for session-to-repository Q&A execution context resolution."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.models.repository import RepositoryAnalysisStatus
from app.services.qa_service import (
    QAGitHubRepositoryIdMissingError,
    QARepositoryNotReadyError,
    QAService,
    QASessionNotFoundError,
)


def _chat_session(*, status: str, github_repository_id: int | None):
    repository = Mock(
        id=uuid4(),
        analysis_status=status,
        github_repository_id=github_repository_id,
    )
    return Mock(id=uuid4(), repository=repository)


def test_resolves_ready_session_to_qa_execution_context() -> None:
    chat_session = _chat_session(
        status=RepositoryAnalysisStatus.READY.value,
        github_repository_id=123,
    )
    store = Mock()
    store.get_with_repository.return_value = chat_session
    service = QAService(store)

    context = service.get_execution_context(chat_session.id)

    assert context.session_id == chat_session.id
    assert context.repository_id == chat_session.repository.id
    assert context.github_repository_id == 123
    store.get_with_repository.assert_called_once_with(chat_session.id)


def test_rejects_missing_chat_session() -> None:
    store = Mock()
    store.get_with_repository.return_value = None

    with pytest.raises(QASessionNotFoundError, match="Chat session not found"):
        QAService(store).get_execution_context(uuid4())


@pytest.mark.parametrize(
    "status",
    [
        RepositoryAnalysisStatus.PENDING.value,
        RepositoryAnalysisStatus.INDEXING.value,
        RepositoryAnalysisStatus.FAILED.value,
    ],
)
def test_rejects_repository_that_is_not_ready(status: str) -> None:
    chat_session = _chat_session(status=status, github_repository_id=123)
    store = Mock()
    store.get_with_repository.return_value = chat_session

    with pytest.raises(QARepositoryNotReadyError, match="analysis must be ready"):
        QAService(store).get_execution_context(chat_session.id)


def test_rejects_ready_repository_without_github_repository_id() -> None:
    chat_session = _chat_session(
        status=RepositoryAnalysisStatus.READY.value,
        github_repository_id=None,
    )
    store = Mock()
    store.get_with_repository.return_value = chat_session

    with pytest.raises(QAGitHubRepositoryIdMissingError, match="GitHub repository ID"):
        QAService(store).get_execution_context(chat_session.id)
