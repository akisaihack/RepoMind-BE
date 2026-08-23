"""API tests for persisted chat session creation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.extensions import db
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import DEFAULT_CHAT_SESSION_TITLE, ChatSession
from app.models.repository import Repository, RepositoryAnalysisStatus


@pytest.fixture(autouse=True)
def session_database(app):
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def _repository(*, status: RepositoryAnalysisStatus) -> Repository:
    return Repository(
        repository_url=f"https://github.com/example/session-api-{uuid4()}.git",
        branch="main",
        analysis_status=status.value,
    )


def _persist_repository(app, *, status: RepositoryAnalysisStatus) -> UUID:
    with app.app_context():
        repository = _repository(status=status)
        db.session.add(repository)
        db.session.commit()
        return repository.id


def _persist_chat_session(app, *, repository_id: UUID, title: str, updated_at: datetime) -> UUID:
    with app.app_context():
        chat_session = ChatSession(
            repository_id=repository_id,
            title=title,
            updated_at=updated_at,
        )
        db.session.add(chat_session)
        db.session.commit()
        return chat_session.id


def _persist_message(
    app,
    *,
    session_id: UUID,
    role: ChatMessageRole,
    content: str,
    created_at: datetime,
    structured_answer: dict | None = None,
) -> UUID:
    with app.app_context():
        message = ChatMessage(
            session_id=session_id,
            role=role.value,
            content=content,
            structured_answer=structured_answer,
            created_at=created_at,
        )
        db.session.add(message)
        db.session.commit()
        return message.id


def test_creates_persisted_session_for_ready_repository(client, app) -> None:
    repository_id = _persist_repository(app, status=RepositoryAnalysisStatus.READY)

    response = client.post(
        "/api/v1/sessions/",
        json={"repo_id": str(repository_id), "title": "  로그인 흐름  "},
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["repo_id"] == str(repository_id)
    assert data["title"] == "로그인 흐름"
    assert data["created_at"]
    assert data["updated_at"]
    with app.app_context():
        chat_session = db.session.get(ChatSession, UUID(data["session_id"]))
        assert chat_session is not None
        assert chat_session.repository_id == repository_id
        assert chat_session.title == "로그인 흐름"


def test_uses_default_title_when_title_is_omitted(client, app) -> None:
    repository_id = _persist_repository(app, status=RepositoryAnalysisStatus.READY)

    response = client.post("/api/v1/sessions/", json={"repo_id": str(repository_id)})

    assert response.status_code == 201
    assert response.get_json()["data"]["title"] == DEFAULT_CHAT_SESSION_TITLE


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        (None, "INVALID_REQUEST"),
        ({}, "INVALID_REPOSITORY_ID"),
        ({"repo_id": 1}, "INVALID_REPOSITORY_ID"),
        ({"repo_id": "not-a-uuid"}, "INVALID_REPOSITORY_ID"),
        ({"repo_id": str(uuid4()), "title": 1}, "INVALID_SESSION_TITLE"),
        ({"repo_id": str(uuid4()), "title": " "}, "INVALID_SESSION_TITLE"),
        ({"repo_id": str(uuid4()), "title": "a" * 256}, "INVALID_SESSION_TITLE"),
    ],
)
def test_rejects_invalid_session_create_request(client, payload, error_code: str) -> None:
    if payload is None:
        response = client.post("/api/v1/sessions/", json=[])
    else:
        response = client.post("/api/v1/sessions/", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == error_code


def test_returns_not_found_for_unknown_repository(client) -> None:
    response = client.post("/api/v1/sessions/", json={"repo_id": str(uuid4())})

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "REPOSITORY_NOT_FOUND"


@pytest.mark.parametrize(
    "status",
    [
        RepositoryAnalysisStatus.PENDING,
        RepositoryAnalysisStatus.INDEXING,
        RepositoryAnalysisStatus.FAILED,
    ],
)
def test_rejects_session_creation_before_repository_is_ready(client, app, status) -> None:
    repository_id = _persist_repository(app, status=status)

    response = client.post("/api/v1/sessions/", json={"repo_id": str(repository_id)})

    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "REPOSITORY_NOT_READY"
    assert error["details"] == {"analysis_status": status.value}
    with app.app_context():
        assert db.session.query(ChatSession).count() == 0


def test_lists_only_repository_sessions_in_recent_activity_order(client, app) -> None:
    repository_id = _persist_repository(app, status=RepositoryAnalysisStatus.READY)
    other_repository_id = _persist_repository(app, status=RepositoryAnalysisStatus.READY)
    now = datetime.now(UTC)
    older_session_id = _persist_chat_session(
        app,
        repository_id=repository_id,
        title="이전 대화",
        updated_at=now - timedelta(minutes=1),
    )
    newer_session_id = _persist_chat_session(
        app,
        repository_id=repository_id,
        title="최근 대화",
        updated_at=now,
    )
    _persist_chat_session(
        app,
        repository_id=other_repository_id,
        title="다른 레포지토리 대화",
        updated_at=now + timedelta(minutes=1),
    )

    response = client.get(f"/api/v1/sessions/?repo_id={repository_id}")

    assert response.status_code == 200
    sessions = response.get_json()["data"]["sessions"]
    assert [session["session_id"] for session in sessions] == [
        str(newer_session_id),
        str(older_session_id),
    ]
    assert all(session["repo_id"] == str(repository_id) for session in sessions)


def test_returns_not_found_when_listing_unknown_repository_sessions(client) -> None:
    response = client.get(f"/api/v1/sessions/?repo_id={uuid4()}")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "REPOSITORY_NOT_FOUND"


def test_returns_empty_message_history_for_session_without_messages(client, app) -> None:
    repository_id = _persist_repository(app, status=RepositoryAnalysisStatus.READY)
    session_id = _persist_chat_session(
        app,
        repository_id=repository_id,
        title="빈 대화",
        updated_at=datetime.now(UTC),
    )

    response = client.get(f"/api/v1/sessions/{session_id}/messages")

    assert response.status_code == 200
    assert response.get_json()["data"] == {"session_id": str(session_id), "messages": []}


def test_returns_messages_in_order_with_structured_answer(client, app) -> None:
    repository_id = _persist_repository(app, status=RepositoryAnalysisStatus.READY)
    session_id = _persist_chat_session(
        app,
        repository_id=repository_id,
        title="메시지 이력",
        updated_at=datetime.now(UTC),
    )
    other_session_id = _persist_chat_session(
        app,
        repository_id=repository_id,
        title="다른 메시지 이력",
        updated_at=datetime.now(UTC),
    )
    now = datetime.now(UTC)
    user_message_id = _persist_message(
        app,
        session_id=session_id,
        role=ChatMessageRole.USER,
        content="질문입니다.",
        created_at=now - timedelta(minutes=1),
    )
    answer = {"summary": "답변입니다.", "claims": []}
    assistant_message_id = _persist_message(
        app,
        session_id=session_id,
        role=ChatMessageRole.ASSISTANT,
        content="답변입니다.",
        structured_answer=answer,
        created_at=now,
    )
    _persist_message(
        app,
        session_id=other_session_id,
        role=ChatMessageRole.USER,
        content="다른 세션 질문입니다.",
        created_at=now,
    )

    response = client.get(f"/api/v1/sessions/{session_id}/messages")

    assert response.status_code == 200
    messages = response.get_json()["data"]["messages"]
    assert [message["message_id"] for message in messages] == [
        str(user_message_id),
        str(assistant_message_id),
    ]
    assert messages[0]["structured_answer"] is None
    assert messages[1]["structured_answer"] == answer


def test_returns_not_found_for_unknown_session_history(client) -> None:
    response = client.get(f"/api/v1/sessions/{uuid4()}/messages")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "SESSION_NOT_FOUND"
