"""Tests for Chat Query API endpoint."""

from uuid import UUID, uuid4

from app.extensions import db
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import ChatSession
from app.models.repository import Repository, RepositoryAnalysisStatus


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


def test_chat_query_persists_question_and_mock_answer(client, app):
    """Test submitting a chat query and receiving a structured answer."""
    session_id = _create_session(app)
    response = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"question": "회원 탈퇴는 어떻게 해?"}
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data["success"] is True
    
    # Check for the core fields expected by the frontend StructuredAnswer
    response_data = data["data"]
    assert "summary" in response_data
    assert isinstance(response_data["claims"], list)
    assert isinstance(response_data["evidence"], list)
    assert "confidence" in response_data
    
    # Check graph structure
    assert "graph" in response_data
    assert isinstance(response_data["graph"]["nodes"], list)
    assert isinstance(response_data["graph"]["edges"], list)

    history_response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert history_response.status_code == 200
    messages = history_response.get_json()["data"]["messages"]
    assert [(message["role"], message["content"]) for message in messages] == [
        (ChatMessageRole.USER.value, "회원 탈퇴는 어떻게 해?"),
        (ChatMessageRole.ASSISTANT.value, response_data["summary"]),
    ]
    assert messages[0]["structured_answer"] is None
    assert messages[1]["structured_answer"] == response_data

    with app.app_context():
        assert db.session.query(ChatMessage).count() == 2


def test_chat_query_rejects_unknown_question_kind(client):
    response = client.post(
        f"/api/v1/sessions/{uuid4()}/chat",
        json={"question": "호출 흐름을 알려줘", "question_kind": "unknown"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_QUESTION_KIND"


def test_chat_query_rejects_unknown_session(client):
    response = client.post(
        f"/api/v1/sessions/{uuid4()}/chat",
        json={"question": "호출 흐름을 알려줘"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "SESSION_NOT_FOUND"
