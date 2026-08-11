"""Repository RDB API tests."""

from uuid import UUID

import pytest

from app.extensions import db
from app.models.repository import Repository


@pytest.fixture(autouse=True)
def repository_database(app):
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def _create_repository(client, *, branch: str = "develop") -> dict:
    response = client.post(
        "/api/v1/repositories/",
        json={
            "repository_url": "https://github.com/owner/repository.git/",
            "branch": branch,
        },
    )
    assert response.status_code == 201
    return response.get_json()["data"]


def test_create_repository_persists_pending_registration(client, app) -> None:
    data = _create_repository(client)

    assert data["repository_url"] == "https://github.com/owner/repository"
    assert data["branch"] == "develop"
    assert data["analysis_status"] == "pending"
    assert data["latest_analyzed_sha"] is None

    with app.app_context():
        repository = db.session.get(Repository, UUID(data["id"]))
        assert repository is not None
        assert repository.repository_url == data["repository_url"]


def test_lists_and_gets_registered_repositories(client) -> None:
    created = _create_repository(client)

    list_response = client.get("/api/v1/repositories/")
    detail_response = client.get(f"/api/v1/repositories/{created['id']}")

    assert list_response.status_code == 200
    assert list_response.get_json()["data"]["repositories"] == [created]
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"] == created


def test_rejects_duplicate_repository_and_branch(client) -> None:
    _create_repository(client)

    response = client.post(
        "/api/v1/repositories/",
        json={
            "repository_url": "https://github.com/owner/repository",
            "branch": "develop",
        },
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "REPOSITORY_ALREADY_EXISTS"


@pytest.mark.parametrize(
    "payload, error_code",
    [
        ({"repository_url": "http://github.com/owner/repository"}, "INVALID_REPOSITORY_URL"),
        ({"repository_url": "https://gitlab.com/owner/repository"}, "INVALID_REPOSITORY_URL"),
        ({"repository_url": "https://github.com/owner"}, "INVALID_REPOSITORY_URL"),
        (
            {"repository_url": "https://github.com/owner/repository", "branch": " "},
            "INVALID_BRANCH",
        ),
    ],
)
def test_rejects_invalid_repository_registration(client, payload, error_code: str) -> None:
    response = client.post("/api/v1/repositories/", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == error_code


def test_returns_not_found_for_unknown_repository(client) -> None:
    response = client.get("/api/v1/repositories/6a0a1d1d-7c40-4d17-a8ba-64f82411f995")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "REPOSITORY_NOT_FOUND"
