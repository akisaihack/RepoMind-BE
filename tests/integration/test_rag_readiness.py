"""Opt-in readiness check against configured PostgreSQL and Neo4j services."""

import os

import pytest

from app import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to use configured RAG services",
    ),
]


def test_rag_readiness_uses_configured_services() -> None:
    app = create_app()

    response = app.test_client().get("/api/v1/health/readiness")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "ready"
