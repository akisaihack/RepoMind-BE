"""Neo4j graph constraint initialization tests."""

from unittest.mock import Mock

from app.graph.schema import CONSTRAINTS, initialize_github_graph_schema


def test_initializes_every_constraint_idempotently() -> None:
    client = Mock()

    initialize_github_graph_schema(client)

    assert client.execute_query.call_count == len(CONSTRAINTS)
    assert all("IF NOT EXISTS" in call.args[0] for call in client.execute_query.call_args_list)
