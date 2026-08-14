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
    file_node = GraphNode(
        "100:file:src/App.java",
        "File",
        {"path": "src/App.java", "githubRepositoryId": 100},
    )
    class_node = GraphNode(
        "100:class:src/App.java:0",
        "Class",
        {"name": "App", "githubRepositoryId": 100},
    )
    return GraphDocument(
        nodes=(file_node, class_node),
        edges=(GraphEdge("DECLARES", file_node.id, class_node.id, {}),),
    )


def _transactional_client() -> tuple[Mock, Mock]:
    client = Mock()
    transaction = Mock()

    def execute(work):
        return work(transaction)

    client.execute_write.side_effect = execute
    return client, transaction


def _save(repository: CodeGraphRepository, document: GraphDocument) -> int:
    return repository.save(
        document,
        github_repository_id=100,
        analysis_run_id="run-current",
    )


def test_merges_nodes_before_relationships() -> None:
    client, transaction = _transactional_client()

    skipped = _save(CodeGraphRepository(client), _document())

    assert skipped == 0
    client.execute_write.assert_called_once()
    assert transaction.run.call_count == 5
    queries = [call.args[0] for call in transaction.run.call_args_list]
    assert "MERGE (node:File {key: row.key})" in queries[0]
    assert "SET node.analysisRunId" not in queries[0]
    assert "SET node.analysisRunId = $analysisRunId" in queries[1]
    assert "MERGE (source)-[relation:DECLARES]->(target)" in queries[2]
    assert "SET relation.analysisRunId = $analysisRunId" in queries[2]
    assert "DELETE relation" in queries[3]
    assert "DETACH DELETE node" in queries[4]
    assert transaction.run.call_args_list[3].kwargs["repositoryId"] == 100
    assert transaction.run.call_args_list[3].kwargs["analysisRunId"] == "run-current"
    assert transaction.run.return_value.consume.call_count == 5


def test_skips_unresolved_external_relationship() -> None:
    document = _document()
    document = GraphDocument(
        nodes=document.nodes,
        edges=document.edges
        + (GraphEdge("EXTENDS", document.nodes[1].id, "External", {"external": True}),),
    )
    client, _ = _transactional_client()

    assert _save(CodeGraphRepository(client), document) == 1


def test_rejects_unknown_labels_and_relationships() -> None:
    client = Mock()
    with pytest.raises(CodeGraphValidationError, match="node label"):
        _save(
            CodeGraphRepository(client),
            GraphDocument((GraphNode("x", "Injected", {}),), ()),
        )
    with pytest.raises(CodeGraphValidationError, match="relationship type"):
        document = _document()
        _save(
            CodeGraphRepository(client),
            GraphDocument(document.nodes, (GraphEdge("BAD", *[n.id for n in document.nodes], {}),)),
        )


def test_converts_neo4j_errors() -> None:
    client = Mock()
    error = Neo4jError("down")
    client.execute_write.side_effect = error

    with pytest.raises(CodeGraphPersistenceError, match="source-code graph") as raised:
        _save(CodeGraphRepository(client), _document())

    assert raised.value.__cause__ is error


@pytest.mark.parametrize("failure_call", [2, 3])
def test_node_or_relationship_failure_aborts_the_transaction(failure_call: int) -> None:
    client, transaction = _transactional_client()
    error = Neo4jError("batch failed")
    successful_result = Mock()

    def execute_with_failure(work):
        results = iter([*[successful_result] * (failure_call - 1), error])

        def run(*args, **kwargs):
            result = next(results)
            if isinstance(result, Exception):
                raise result
            return result

        transaction.run.side_effect = run
        return work(transaction)

    client.execute_write.side_effect = execute_with_failure

    with pytest.raises(CodeGraphPersistenceError) as raised:
        _save(CodeGraphRepository(client), _document())

    assert raised.value.__cause__ is error


def test_splits_large_node_batches_inside_one_transaction() -> None:
    client, transaction = _transactional_client()
    nodes = tuple(
        GraphNode(
            f"100:file:{index}.java",
            "File",
            {"githubRepositoryId": 100},
        )
        for index in range(5)
    )

    _save(CodeGraphRepository(client, batch_size=2), GraphDocument(nodes, ()))

    client.execute_write.assert_called_once()
    row_calls = [call for call in transaction.run.call_args_list if "rows" in call.kwargs]
    assert [len(call.kwargs["rows"]) for call in row_calls] == [2, 2, 1]


def test_empty_document_runs_cleanup_transaction() -> None:
    client, transaction = _transactional_client()

    assert _save(CodeGraphRepository(client), GraphDocument((), ())) == 0
    client.execute_write.assert_called_once()
    assert transaction.run.call_count == 2


def test_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError, match="batch size"):
        CodeGraphRepository(Mock(), batch_size=0)


def test_rejects_nodes_from_another_repository() -> None:
    document = GraphDocument(
        (GraphNode("101:file:a.java", "File", {"githubRepositoryId": 101}),),
        (),
    )

    with pytest.raises(CodeGraphValidationError, match="outside repository"):
        _save(CodeGraphRepository(Mock()), document)


def test_rejects_empty_analysis_run_id() -> None:
    with pytest.raises(CodeGraphValidationError, match="run ID"):
        CodeGraphRepository(Mock()).save(
            GraphDocument((), ()),
            github_repository_id=100,
            analysis_run_id="",
        )
