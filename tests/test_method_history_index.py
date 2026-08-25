from pathlib import Path
from unittest.mock import Mock

from app.dtos.graph import GraphDocument, GraphEdge, GraphNode
from app.services.git_clone import GitCommit, GitFileChange
from app.services.method_history_index import (
    MethodHistoryIndexer,
    MethodHistoryLimitError,
    _commit_document,
    _with_version_ancestry,
)


def _version(method_key: str, version_key: str) -> GraphDocument:
    method = GraphNode(method_key, "Method", {"githubRepositoryId": 1})
    version = GraphNode(
        version_key,
        "MethodVersion",
        {"methodKey": method_key, "contentHash": version_key},
    )
    commit = GraphNode("1:commit:head", "Commit", {"sha": "head"})
    return GraphDocument(
        (method, version, commit),
        (
            GraphEdge("HAS_VERSION", method_key, version_key, {}),
            GraphEdge("INTRODUCED_IN", version_key, commit.id, {}),
        ),
    )


def test_adds_derived_from_only_when_method_content_changes() -> None:
    previous = GraphNode("version:old", "MethodVersion", {"methodKey": "method:a"})
    document = _version("method:a", "version:new")

    result = _with_version_ancestry(
        document,
        {"method:a": document.nodes[1]},
        {"method:a": previous},
    )

    assert previous in result.nodes
    assert GraphEdge("DERIVED_FROM", "version:new", "version:old", {}) in result.edges


def test_preserves_first_parent_commit_chain() -> None:
    document = _commit_document(1, GitCommit("child", "parent"))

    assert GraphEdge("PARENT", "1:commit:child", "1:commit:parent", {}) in document.edges


def test_indexes_changed_files_and_explicit_deletions(monkeypatch) -> None:
    git = Mock()
    graph = Mock()
    commit = GitCommit("head", "parent")
    git.list_first_parent_commits.return_value = [commit]
    git.list_changed_files.return_value = [GitFileChange("M", "src/App.java")]
    indexer = MethodHistoryIndexer(git, graph)
    old = _version("method:deleted", "version:old")
    indexer._load_baseline = Mock()  # type: ignore[method-assign]
    indexer._load_baseline.side_effect = lambda *args: (
        args[3].update({"src/App.java": {"method:deleted": old.nodes[1]}}),
        args[4].update({"method:deleted": old.nodes[1]}),
    )
    monkeypatch.setattr(indexer, "_parse_file", lambda *args: _version("method:new", "v1"))

    result = indexer.index(1, Path("/repo"), after_sha="parent")

    graph.mark_methods_deleted.assert_called_once_with(1, "head", ["method:deleted"])
    assert result.commits == 1
    assert result.versions == 1
    assert result.deletions == 1


def test_rejects_commit_with_too_many_changed_source_files() -> None:
    git = Mock()
    git.list_first_parent_commits.return_value = [GitCommit("head", None)]
    git.list_changed_files.return_value = [
        GitFileChange("A", "A.java"),
        GitFileChange("A", "B.java"),
    ]
    indexer = MethodHistoryIndexer(git, Mock(), max_changed_files=1)

    try:
        indexer.index(1, Path("/repo"))
    except MethodHistoryLimitError as exc:
        assert "head" in str(exc)
    else:
        raise AssertionError("expected MethodHistoryLimitError")
