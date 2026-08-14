"""Local Git checkout and GitHub repository identity validation tests."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.services.repository_identity import (
    GitRemoteError,
    RepositoryIdentityMismatchError,
    RepositoryIdentityValidator,
    get_origin_url,
    normalize_github_repository_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/OpenAI/codex.git",
        "http://github.com/OpenAI/codex",
        "git@github.com:OpenAI/codex.git",
        "ssh://git@github.com/OpenAI/codex.git",
        "git://github.com/OpenAI/codex.git",
    ],
)
def test_normalizes_supported_github_remote_urls(url: str) -> None:
    assert normalize_github_repository_url(url) == "OpenAI/codex"


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/OpenAI/codex.git",
        "github.com/OpenAI/codex",
        "https://github.com/OpenAI/codex/extra",
    ],
)
def test_rejects_unsupported_remote_urls(url: str) -> None:
    with pytest.raises(GitRemoteError):
        normalize_github_repository_url(url)


def test_reads_origin_remote_from_requested_checkout() -> None:
    completed = subprocess.CompletedProcess([], 0, "git@github.com:OpenAI/codex.git\n", "")
    with patch("app.services.repository_identity.subprocess.run", return_value=completed) as run:
        assert get_origin_url(Path("/repo")) == "git@github.com:OpenAI/codex.git"

    run.assert_called_once_with(
        ["git", "-C", "/repo", "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_missing_origin_is_rejected() -> None:
    with patch(
        "app.services.repository_identity.subprocess.run",
        side_effect=subprocess.CalledProcessError(2, "git"),
    ):
        with pytest.raises(GitRemoteError, match="origin"):
            get_origin_url(Path("/repo"))


def test_prefers_neo4j_repository_identity() -> None:
    neo4j = Mock()
    neo4j.execute_query.return_value = ([{"fullName": "OpenAI/codex"}], None, None)
    github_lookup = Mock()
    validator = RepositoryIdentityValidator(neo4j, github_lookup)

    with patch(
        "app.services.repository_identity.get_origin_url",
        return_value="git@github.com:openai/CODEX.git",
    ):
        identity = validator.validate(123, Path("/repo"))

    assert identity.expected_full_name == "OpenAI/codex"
    assert identity.source == "neo4j"
    github_lookup.assert_not_called()


def test_falls_back_to_github_repository_identity() -> None:
    neo4j = Mock()
    neo4j.execute_query.return_value = ([], None, None)
    github_lookup = Mock(return_value={"id": 123, "full_name": "OpenAI/codex"})
    validator = RepositoryIdentityValidator(neo4j, github_lookup)

    with patch(
        "app.services.repository_identity.get_origin_url",
        return_value="https://github.com/OpenAI/codex.git",
    ):
        identity = validator.validate(123, Path("/repo"))

    assert identity.source == "github"
    github_lookup.assert_called_once_with(123)


def test_repository_mismatch_is_rejected() -> None:
    neo4j = Mock()
    neo4j.execute_query.return_value = ([{"fullName": "OpenAI/codex"}], None, None)
    validator = RepositoryIdentityValidator(neo4j, Mock())

    with (
        patch(
            "app.services.repository_identity.get_origin_url",
            return_value="https://github.com/example/other.git",
        ),
        pytest.raises(RepositoryIdentityMismatchError, match="does not match"),
    ):
        validator.validate(123, Path("/repo"))


def test_explicit_skip_avoids_remote_and_repository_lookups() -> None:
    neo4j = Mock()
    github_lookup = Mock()
    validator = RepositoryIdentityValidator(neo4j, github_lookup)

    identity = validator.validate(123, Path("/not-a-repository"), skip=True)

    assert identity.skipped is True
    assert identity.source == "skipped"
    neo4j.execute_query.assert_not_called()
    github_lookup.assert_not_called()


def test_invalid_repository_id_is_rejected_even_when_validation_is_skipped() -> None:
    validator = RepositoryIdentityValidator(Mock(), Mock())

    with pytest.raises(ValueError, match="positive integer"):
        validator.validate(0, Path("/repo"), skip=True)
