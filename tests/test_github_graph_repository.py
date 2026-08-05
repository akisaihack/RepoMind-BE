"""Neo4j GitHub graph repository tests."""

from unittest.mock import Mock

import pytest
from neo4j.exceptions import Neo4jError

from app.graph.models import GitHubGraphData
from app.graph.repositories.github_history import (
    GitHubHistoryGraphRepository,
    GraphPersistenceError,
)


def test_saves_non_empty_batches_with_parameterized_queries() -> None:
    client = Mock()
    data = GitHubGraphData(
        repositories=(
            {
                "githubRepositoryId": 100,
                "properties": {"name": "repo"},
            },
        ),
        commits=(
            {
                "key": "100:commit:abc123",
                "properties": {"sha": "abc123"},
            },
        ),
    )

    GitHubHistoryGraphRepository(client).save(data)

    assert client.execute_query.call_count == 2
    assert client.execute_query.call_args_list[0].args[1] == {"rows": list(data.repositories)}
    assert "MERGE" in client.execute_query.call_args_list[0].args[0]


def test_converts_neo4j_error() -> None:
    client = Mock()
    client.execute_query.side_effect = Neo4jError("connection failed")
    data = GitHubGraphData(
        repositories=({"githubRepositoryId": 100, "properties": {}},),
    )

    with pytest.raises(GraphPersistenceError, match="development graph"):
        GitHubHistoryGraphRepository(client).save(data)
