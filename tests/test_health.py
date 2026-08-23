"""Health API tests."""

from unittest.mock import MagicMock, patch

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


def _configure_rag_dependencies(client: FlaskClient) -> None:
    client.application.config.update(
        AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com/",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT="test-embedding",
        AZURE_OPENAI_DEPLOYMENT="test-chat",
        NEO4J_URI="neo4j://localhost:7687",
        NEO4J_USERNAME="neo4j",
        NEO4J_PASSWORD="test-password",
    )


def test_rag_readiness_check_reports_ready_dependencies(client: FlaskClient) -> None:
    _configure_rag_dependencies(client)
    database_result = MagicMock()
    database_result.scalar_one.side_effect = [1, True]
    neo4j_client = MagicMock()
    neo4j_client.__enter__.return_value = neo4j_client

    with (
        client.application.app_context(),
        patch.object(db.session, "execute", return_value=database_result),
        patch("app.api.v1.health.Neo4jClient.from_config", return_value=neo4j_client),
    ):
        response = client.get("/api/v1/health/readiness")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {
            "status": "ready",
            "database": "connected",
            "pgvector": "available",
            "neo4j": "connected",
            "azure_openai": "configured",
        },
    }
    neo4j_client.verify_connectivity.assert_called_once()


def test_rag_readiness_check_reports_missing_configuration(client: FlaskClient) -> None:
    _configure_rag_dependencies(client)
    client.application.config["AZURE_OPENAI_DEPLOYMENT"] = None

    response = client.get("/api/v1/health/readiness")

    assert response.status_code == 503
    assert response.get_json()["error"] == {
        "code": "RAG_CONFIGURATION_INCOMPLETE",
        "message": "Required RAG configuration is missing.",
        "details": {"missing": ["AZURE_OPENAI_DEPLOYMENT"]},
    }


def test_rag_readiness_check_reports_database_and_neo4j_failures(client: FlaskClient) -> None:
    _configure_rag_dependencies(client)
    database_error = OperationalError("SELECT 1", {}, Exception("connection failed"))

    with (
        client.application.app_context(),
        patch.object(
            db.session,
            "execute",
            side_effect=database_error,
        ),
    ):
        database_response = client.get("/api/v1/health/readiness")

    assert database_response.status_code == 503
    assert database_response.get_json()["error"]["code"] == "DATABASE_UNAVAILABLE"

    database_result = MagicMock()
    database_result.scalar_one.side_effect = [1, True]
    with (
        client.application.app_context(),
        patch.object(db.session, "execute", return_value=database_result),
        patch(
            "app.api.v1.health.Neo4jClient.from_config",
            side_effect=RuntimeError("connection failed"),
        ),
    ):
        neo4j_response = client.get("/api/v1/health/readiness")

    assert neo4j_response.status_code == 503
    assert neo4j_response.get_json()["error"]["code"] == "NEO4J_UNAVAILABLE"


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
