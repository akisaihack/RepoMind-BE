"""Tests for session-to-repository Q&A execution context resolution."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.dtos.chat import ChatRequest
from app.dtos.question import QuestionKind
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


def test_ask_runs_pipeline_with_explicit_question_kind_and_adapts_response() -> None:
    chat_session = _chat_session(
        status=RepositoryAnalysisStatus.READY.value,
        github_repository_id=123,
    )
    store = Mock()
    store.get_with_repository.return_value = chat_session
    final_state = {
        "answer": {"answer": "호출 흐름입니다.", "intent": "FLOW", "visualization": None},
        "evidence": [],
        "graph_results": {"nodes": [], "edges": []},
        "is_sufficient": False,
    }
    pipeline_runner = Mock(return_value=final_state)
    response_adapter = Mock()
    expected_response = Mock()
    response_adapter.adapt.return_value = expected_response
    service = QAService(
        store,
        pipeline_runner=pipeline_runner,
        response_adapter=response_adapter,
    )

    result = service.ask(
        chat_session.id,
        ChatRequest(question="로그인 흐름을 알려줘", question_kind=QuestionKind.FLOW),
    )

    assert result is expected_response
    pipeline_runner.assert_called_once_with(
        question="로그인 흐름을 알려줘",
        github_repository_id=123,
        conversation_id=str(chat_session.id),
        question_kind=QuestionKind.FLOW,
    )
    response_adapter.adapt.assert_called_once_with(final_state, final_state["answer"])


def test_ask_leaves_question_kind_empty_for_pipeline_classification() -> None:
    chat_session = _chat_session(
        status=RepositoryAnalysisStatus.READY.value,
        github_repository_id=123,
    )
    store = Mock()
    store.get_with_repository.return_value = chat_session
    final_state = {
        "answer": {"answer": "코드는 AuthService에 있습니다.", "intent": "EXPLANATION"},
        "evidence": [],
        "graph_results": {"nodes": [], "edges": []},
        "is_sufficient": False,
    }
    pipeline_runner = Mock(return_value=final_state)
    service = QAService(store, pipeline_runner=pipeline_runner)

    response = service.ask(chat_session.id, ChatRequest(question="로그인 코드는 어디에 있어?"))

    assert response.summary == "코드는 AuthService에 있습니다."
    assert response.confidence.level == "low"
    assert pipeline_runner.call_args.kwargs["question_kind"] is None


def test_ask_propagates_answer_generation_failure() -> None:
    chat_session = _chat_session(
        status=RepositoryAnalysisStatus.READY.value,
        github_repository_id=123,
    )
    store = Mock()
    store.get_with_repository.return_value = chat_session
    pipeline_runner = Mock(side_effect=RuntimeError("answer provider failed"))
    service = QAService(store, pipeline_runner=pipeline_runner)

    with pytest.raises(RuntimeError, match="answer provider failed"):
        service.ask(chat_session.id, ChatRequest(question="로그인 흐름을 알려줘"))
