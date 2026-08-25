"""Neo4j source-code graph repository tests."""

from unittest.mock import Mock

import pytest
from neo4j.exceptions import Neo4jError

from app.dtos.graph import GraphDocument, GraphEdge, GraphNode
from app.graph.repositories.code_graph import (
    CodeGraphPersistenceError,
    CodeGraphRepository,
    CodeGraphValidationError,
    _introduced_in_query,
    _mark_deleted_methods_query,
)


def _document() -> GraphDocument:
    file_node = GraphNode("100:file:src/App.java", "File", {"path": "src/App.java"})
    class_node = GraphNode("100:class:src/App.java:0", "Class", {"name": "App"})
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


def test_merges_nodes_before_relationships() -> None:
    client, transaction = _transactional_client()

    skipped = CodeGraphRepository(client).save(_document())

    assert skipped == 0
    client.execute_write.assert_called_once()
    assert transaction.run.call_count == 3
    queries = [call.args[0] for call in transaction.run.call_args_list]
    assert "MERGE (node:File {key: row.key})" in queries[0]
    assert "MERGE (source)-[relation:DECLARES]->(target)" in queries[2]
    assert transaction.run.return_value.consume.call_count == 3


def test_skips_unresolved_external_relationship() -> None:
    document = _document()
    document = GraphDocument(
        nodes=document.nodes,
        edges=document.edges
        + (GraphEdge("EXTENDS", document.nodes[1].id, "External", {"external": True}),),
    )
    client, _ = _transactional_client()

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
    error = Neo4jError("down")
    client.execute_write.side_effect = error

    with pytest.raises(CodeGraphPersistenceError, match="source-code graph") as raised:
        CodeGraphRepository(client).save(_document())

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
        CodeGraphRepository(client).save(_document())

    assert raised.value.__cause__ is error


def test_splits_large_node_batches_inside_one_transaction() -> None:
    client, transaction = _transactional_client()
    nodes = tuple(GraphNode(f"100:file:{index}.java", "File", {}) for index in range(5))

    CodeGraphRepository(client, batch_size=2).save(GraphDocument(nodes, ()))

    client.execute_write.assert_called_once()
    assert [len(call.kwargs["rows"]) for call in transaction.run.call_args_list] == [2, 2, 1]


def test_empty_document_does_not_open_transaction() -> None:
    client = Mock()

    assert CodeGraphRepository(client).save(GraphDocument((), ())) == 0
    client.execute_write.assert_not_called()


def test_records_deleted_methods_when_saving_a_commit_snapshot() -> None:
    client, transaction = _transactional_client()

    CodeGraphRepository(client).save(
        _document(), github_repository_id=100, commit_hash="abc123"
    )

    last_call = transaction.run.call_args_list[-1]
    assert "DELETED_IN" in last_call.args[0]
    assert last_call.kwargs == {
        "repositoryId": 100,
        "commitKey": "100:commit:abc123",
        "activeMethodKeys": [],
    }


def test_partial_history_save_does_not_mark_unrelated_methods_deleted() -> None:
    client, transaction = _transactional_client()

    CodeGraphRepository(client).save(
        _document(),
        github_repository_id=100,
        commit_hash="abc123",
        mark_missing_deleted=False,
    )

    assert all("DELETED_IN" not in call.args[0] for call in transaction.run.call_args_list)


def test_marks_only_selected_methods_deleted() -> None:
    client, transaction = _transactional_client()

    CodeGraphRepository(client).mark_methods_deleted(100, "abc123", ["method:one"])

    call = transaction.run.call_args
    assert "UNWIND $methodKeys" in call.args[0]
    assert call.kwargs["methodKeys"] == ["method:one"]


def test_history_write_queries_do_not_materialize_unbounded_paths() -> None:
    for query in (_introduced_in_query(), _mark_deleted_methods_query()):
        assert "MATCH path" not in query
        assert "introPath" not in query
        assert "deletePath" not in query
        assert "length(" not in query
        assert "EXISTS {" in query


def test_pre_resolved_introduction_is_saved_without_ancestry_traversal() -> None:
    client, transaction = _transactional_client()
    method = GraphNode("method:a", "Method", {})
    version = GraphNode("version:a", "MethodVersion", {})
    commit = GraphNode("commit:a", "Commit", {})
    document = GraphDocument(
        (method, version, commit),
        (
            GraphEdge("HAS_VERSION", method.id, version.id, {}),
            GraphEdge("INTRODUCED_IN", version.id, commit.id, {}),
        ),
    )

    CodeGraphRepository(client).save(
        document,
        resolve_introduction_history=False,
    )

    introduction_query = next(
        call.args[0]
        for call in transaction.run.call_args_list
        if "relation:INTRODUCED_IN" in call.args[0]
    )
    assert "PARENT*0.." not in introduction_query
    assert "MERGE (source)-[relation:INTRODUCED_IN]->(target)" in introduction_query


def test_resolves_nearest_method_version_and_deleted_state() -> None:
    client = Mock()
    version = {"key": "method:version:hash"}
    client.execute_query.return_value = (
        [{"version": version, "eventType": "version", "distance": 1}],
        None,
        None,
    )
    repository = CodeGraphRepository(client)

    assert repository.find_method_version_at_commit(100, "method", "abc123") == version

    client.execute_query.return_value = (
        [{"version": None, "eventType": "deleted", "distance": 0}],
        None,
        None,
    )
    assert repository.find_method_version_at_commit(100, "method", "def456") is None


def test_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError, match="batch size"):
        CodeGraphRepository(Mock(), batch_size=0)
