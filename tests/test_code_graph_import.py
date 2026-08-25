"""Code graph import repository identity validation tests."""

from unittest.mock import Mock

import pytest

from app.services.code_graph_import import CodeGraphImportService
from app.services.repository_identity import (
    RepositoryIdentity,
    RepositoryIdentityMismatchError,
)


def test_validates_repository_before_saving(tmp_path) -> None:
    graph_repository = Mock()
    graph_repository.save.return_value = 0
    validator = Mock()
    identity = RepositoryIdentity(123, "OpenAI/codex", "OpenAI/codex", "neo4j")
    validator.validate.return_value = identity
    callback = Mock()

    result = CodeGraphImportService(graph_repository, validator, callback).import_repository(
        123, tmp_path, "abc123"
    )

    validator.validate.assert_called_once_with(123, tmp_path.resolve(), skip=False)
    callback.assert_called_once_with(identity)
    graph_repository.save.assert_called_once()
    graph_repository.save.assert_called_once_with(
        graph_repository.save.call_args.args[0],
        github_repository_id=123,
        commit_hash="abc123",
        mark_missing_deleted=True,
    )
    assert result.commit_hash == "abc123"
    assert result.repository_full_name == "OpenAI/codex"
    assert result.repository_validation_source == "neo4j"


def test_repository_mismatch_stops_before_graph_save(tmp_path) -> None:
    graph_repository = Mock()
    validator = Mock()
    validator.validate.side_effect = RepositoryIdentityMismatchError("mismatch")

    with pytest.raises(RepositoryIdentityMismatchError):
        CodeGraphImportService(graph_repository, validator).import_repository(
            123, tmp_path, "abc123"
        )

    graph_repository.save.assert_not_called()


def test_explicit_skip_is_forwarded_to_validator(tmp_path) -> None:
    graph_repository = Mock()
    graph_repository.save.return_value = 0
    validator = Mock()
    validator.validate.return_value = RepositoryIdentity(123, None, None, "skipped", True)

    result = CodeGraphImportService(graph_repository, validator).import_repository(
        123, tmp_path, "abc123", skip_repository_validation=True
    )

    validator.validate.assert_called_once_with(123, tmp_path.resolve(), skip=True)
    assert result.repository_validation_skipped is True


def test_snapshot_can_skip_version_history_and_deletion_resolution(
    tmp_path, monkeypatch
) -> None:
    from app.dtos.graph import GraphDocument, GraphEdge, GraphNode

    graph_repository = Mock()
    graph_repository.save.return_value = 0
    validator = Mock()
    validator.validate.return_value = RepositoryIdentity(123, None, None, "skipped", True)
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
    monkeypatch.setattr(
        "app.services.code_graph_import.resolve_cross_file_references",
        lambda documents: document,
    )

    CodeGraphImportService(graph_repository, validator).import_repository(
        123,
        tmp_path,
        "abc123",
        persist_version_history=False,
        mark_missing_deleted=False,
    )

    saved_document = graph_repository.save.call_args.args[0]
    assert all(edge.type != "INTRODUCED_IN" for edge in saved_document.edges)
    assert graph_repository.save.call_args.kwargs["mark_missing_deleted"] is False
