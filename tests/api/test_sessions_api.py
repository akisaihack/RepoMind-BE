"""API tests for persisted chat session creation."""

from uuid import UUID, uuid4

import pytest

from app.extensions import db
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
