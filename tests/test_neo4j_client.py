"""Neo4j client tests."""

from unittest.mock import Mock, patch

import pytest

from app.clients.neo4j import Neo4jClient


def test_neo4j_client_creates_driver_and_verifies_connectivity() -> None:
    driver = Mock()
    config = {
        "NEO4J_URI": "neo4j://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "test-password",
    }

    with patch("app.clients.neo4j.GraphDatabase.driver", return_value=driver) as create_driver:
        with Neo4jClient.from_config(config) as client:
            client.verify_connectivity()

    create_driver.assert_called_once_with(
        "neo4j://localhost:7687",
        auth=("neo4j", "test-password"),
    )
    driver.verify_connectivity.assert_called_once_with()
    driver.close.assert_called_once_with()


def test_neo4j_client_rejects_missing_configuration() -> None:
    with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
        Neo4jClient.from_config(
            {
                "NEO4J_URI": "neo4j://localhost:7687",
                "NEO4J_USERNAME": "neo4j",
            }
        )
