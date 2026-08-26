"""Tests for the Chat Query API endpoint."""

from dataclasses import asdict
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from app.dtos.chat import ChatResponseData, Confidence, GraphData
from app.errors import APIError
from app.extensions import db
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import ChatSession
from app.models.repository import Repository, RepositoryAnalysisStatus
from app.services.qa_service import (
    QAGitHubRepositoryIdMissingError,
    QARepositoryNotReadyError,
    QASessionNotFoundError,
)


def _create_session(app) -> UUID:
    with app.app_context():
        repository = Repository(
            repository_url=f"https://github.com/repomind/chat-{uuid4()}.git",
            branch="main",
            analysis_status=RepositoryAnalysisStatus.READY.value,
        )
        chat_session = ChatSession(repository=repository, title="테스트 대화")
        db.session.add(chat_session)
        db.session.commit()
        return chat_session.id


def _qa_response() -> ChatResponseData:
    return ChatResponseData(
        questionKind="flow",
        summary="회원 탈퇴 요청은 MemberService에서 처리합니다.",
        claims=[],
        evidence=[],
        confidence=Confidence(level="low", reason="테스트 응답입니다."),
        graph=GraphData(),
    )


def test_chat_query_runs_qa_service_and_persists_structured_answer(client, app) -> None:
    session_id = _create_session(app)
    qa_service = Mock()
    qa_service.ask.return_value = _qa_response()

    with patch("app.api.v1.chat._get_qa_service", return_value=qa_service):
        response = client.post(
            f"/api/v1/sessions/{session_id}/chat",
            json={"question": "회원 탈퇴는 어떻게 해?", "question_kind": "flow"},
        )

    assert response.status_code == 200
    response_data = response.get_json()["data"]
    assert response_data == asdict(_qa_response())
    qa_service.ask.assert_called_once()
    asked_session_id, asked_request = qa_service.ask.call_args.args
    assert asked_session_id == session_id
    assert asked_request.question == "회원 탈퇴는 어떻게 해?"
    assert asked_request.question_kind is not None
    assert asked_request.question_kind.value == "flow"

    history_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    messages = history_response.get_json()["data"]["messages"]
    assert [(message["role"], message["content"]) for message in messages] == [
        (ChatMessageRole.USER.value, "회원 탈퇴는 어떻게 해?"),
        (ChatMessageRole.ASSISTANT.value, response_data["summary"]),
    ]
    assert messages[0]["structured_answer"] is None
    assert messages[1]["structured_answer"] == response_data

    with app.app_context():
        assert db.session.query(ChatMessage).count() == 2


def test_chat_query_rejects_unknown_question_kind(client) -> None:
    response = client.post(
        f"/api/v1/sessions/{uuid4()}/chat",
        json={"question": "호출 흐름을 알려줘", "question_kind": "unknown"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_QUESTION_KIND"


def test_chat_query_maps_missing_session(client) -> None:
    qa_service = Mock()
    qa_service.ask.side_effect = QASessionNotFoundError()

    with patch("app.api.v1.chat._get_qa_service", return_value=qa_service):
        response = client.post(
            f"/api/v1/sessions/{uuid4()}/chat",
            json={"question": "호출 흐름을 알려줘"},
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_chat_query_maps_qa_preconditions_and_pipeline_errors(client) -> None:
    session_id = uuid4()
    cases = [
        (QARepositoryNotReadyError(), 409, "REPOSITORY_NOT_READY"),
        (QAGitHubRepositoryIdMissingError(), 409, "REPOSITORY_NOT_ANALYZED"),
        (
            APIError("ANSWER_PROVIDER_ERROR", "provider failed", status=502),
            502,
            "ANSWER_PROVIDER_ERROR",
        ),
        (RuntimeError("neo4j unavailable"), 502, "QA_PIPELINE_FAILED"),
    ]

    for error, status_code, error_code in cases:
        qa_service = Mock()
        qa_service.ask.side_effect = error
        with patch("app.api.v1.chat._get_qa_service", return_value=qa_service):
            response = client.post(
                f"/api/v1/sessions/{session_id}/chat",
                json={"question": "호출 흐름을 알려줘"},
            )

        assert response.status_code == status_code
        assert response.get_json()["error"]["code"] == error_code
