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
        123, tmp_path
    )

    validator.validate.assert_called_once_with(123, tmp_path.resolve(), skip=False)
    callback.assert_called_once_with(identity)
    graph_repository.save.assert_called_once()
    save_call = graph_repository.save.call_args
    assert save_call.kwargs["github_repository_id"] == 123
    assert save_call.kwargs["analysis_run_id"] == result.analysis_run_id
    assert result.analysis_run_id
    assert result.repository_full_name == "OpenAI/codex"
    assert result.repository_validation_source == "neo4j"


def test_repository_mismatch_stops_before_graph_save(tmp_path) -> None:
    graph_repository = Mock()
    validator = Mock()
    validator.validate.side_effect = RepositoryIdentityMismatchError("mismatch")

    with pytest.raises(RepositoryIdentityMismatchError):
        CodeGraphImportService(graph_repository, validator).import_repository(123, tmp_path)

    graph_repository.save.assert_not_called()


def test_explicit_skip_is_forwarded_to_validator(tmp_path) -> None:
    graph_repository = Mock()
    graph_repository.save.return_value = 0
    validator = Mock()
    validator.validate.return_value = RepositoryIdentity(123, None, None, "skipped", True)

    result = CodeGraphImportService(graph_repository, validator).import_repository(
        123, tmp_path, skip_repository_validation=True
    )

    validator.validate.assert_called_once_with(123, tmp_path.resolve(), skip=True)
    assert result.repository_validation_skipped is True
