"""Health API tests."""

from flask.testing import FlaskClient


def test_health_check(client: FlaskClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {"status": "healthy"},
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
