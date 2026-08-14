"""Neo4j source-code graph repository tests."""

from unittest.mock import Mock

import pytest
from neo4j.exceptions import Neo4jError

from app.dtos.graph import GraphDocument, GraphEdge, GraphNode
from app.graph.repositories.code_graph import (
    CodeGraphPersistenceError,
    CodeGraphRepository,
    CodeGraphValidationError,
)


def _document() -> GraphDocument:
    file_node = GraphNode("100:file:src/App.java", "File", {"path": "src/App.java"})
    class_node = GraphNode("100:class:src/App.java:0", "Class", {"name": "App"})
    return GraphDocument(
        nodes=(file_node, class_node),
        edges=(GraphEdge("DECLARES", file_node.id, class_node.id, {}),),
    )


def test_merges_nodes_before_relationships() -> None:
    client = Mock()

    skipped = CodeGraphRepository(client).save(_document())

    assert skipped == 0
    assert client.execute_query.call_count == 3
    queries = [call.args[0] for call in client.execute_query.call_args_list]
    assert "MERGE (node:File {key: row.key})" in queries[0]
    assert "MERGE (source)-[relation:DECLARES]->(target)" in queries[2]


def test_skips_unresolved_external_relationship() -> None:
    document = _document()
    document = GraphDocument(
        nodes=document.nodes,
        edges=document.edges
        + (GraphEdge("EXTENDS", document.nodes[1].id, "External", {"external": True}),),
    )
    client = Mock()

    assert CodeGraphRepository(client).save(document) == 1


def test_rejects_unknown_labels_and_relationships() -> None:
    client = Mock()
    with pytest.raises(CodeGraphValidationError, match="node label"):
        CodeGraphRepository(client).save(GraphDocument((GraphNode("x", "Injected", {}),), ()))
    with pytest.raises(CodeGraphValidationError, match="relationship type"):
        document = _document()
        CodeGraphRepository(client).save(
            GraphDocument(document.nodes, (GraphEdge("BAD", *[n.id for n in document.nodes], {}),))
        )


def test_converts_neo4j_errors() -> None:
    client = Mock()
    client.execute_query.side_effect = Neo4jError("down")

    with pytest.raises(CodeGraphPersistenceError, match="source-code graph"):
        CodeGraphRepository(client).save(_document())
