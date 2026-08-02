"""Health API tests."""

from unittest.mock import patch

from flask.testing import FlaskClient
from sqlalchemy.exc import OperationalError

from app.extensions import db


def test_health_check(client: FlaskClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {"status": "healthy"},
    }


def test_database_health_check(client: FlaskClient) -> None:
    response = client.get("/api/v1/health/db")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {
            "status": "healthy",
            "database": "connected",
        },
    }


def test_database_health_check_handles_connection_error(client: FlaskClient) -> None:
    error = OperationalError("SELECT 1", {}, Exception("connection failed"))

    with (
        client.application.app_context(),
        patch.object(
            db.session,
            "execute",
            side_effect=error,
        ),
    ):
        response = client.get("/api/v1/health/db")

    assert response.status_code == 503
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "The database connection is unavailable.",
        },
    }


def test_not_found_uses_common_error_response(client: FlaskClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested URL was not found on the server. If you entered the URL "
            "manually please check your spelling and try again.",
        },
    }
