import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.git_clone import (
    GitCloneError,
    GitCloneService,
    GitCommit,
    GitHistoryLimitError,
)


@pytest.fixture
def service():
    return GitCloneService()


def test_clone_success(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        
        with service.clone("https://github.com/owner/repo.git", "main") as path:
            assert isinstance(path, Path)
            assert path.is_dir()
            
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert "clone" in args[0]
            assert "https://github.com/owner/repo.git" in args[0]
            assert "main" in args[0]
            assert "--depth" not in args[0]
            assert kwargs["cwd"] == path
            assert kwargs["check"] is True


def test_clone_failure(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128, cmd="git clone", stderr="fatal: repository not found"
        )
        
        with pytest.raises(GitCloneError, match="fatal: repository not found"):
            with service.clone("https://github.com/owner/repo.git", "main"):
                pass


def test_get_commit_hash_success(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="a1b2c3d4e5f6g7h8i9j0\n"
        )
        
        commit_hash = service.get_commit_hash(Path("/fake/repo"))
        assert commit_hash == "a1b2c3d4e5f6g7h8i9j0"
        
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["git", "rev-parse", "HEAD"]
        assert kwargs["cwd"] == Path("/fake/repo")


def test_get_commit_hash_empty_output(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="\n"
        )
        
        with pytest.raises(GitCloneError, match="Git rev-parse returned empty output."):
            service.get_commit_hash(Path("/fake/repo"))


def test_get_commit_hash_failure(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128, cmd="git rev-parse", stderr="fatal: not a git repository"
        )
        
        with pytest.raises(GitCloneError, match="fatal: not a git repository"):
            service.get_commit_hash(Path("/fake/repo"))


def test_lists_first_parent_commits_after_checkpoint(service):
    history = "aaa\nbbb aaa\nccc bbb\n"
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=history
        )

        commits = service.list_first_parent_commits(
            Path("/fake/repo"), after_sha="aaa"
        )

    assert commits == [
        GitCommit("bbb", "aaa"),
        GitCommit("ccc", "bbb"),
    ]


def test_rejects_history_beyond_configured_limit(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="aaa\nbbb aaa\n"
        )

        with pytest.raises(GitHistoryLimitError):
            service.list_first_parent_commits(Path("/fake/repo"), max_commits=1)


def test_parses_modified_deleted_and_renamed_files(service):
    output = b"M\0src/App.java\0D\0src/Old.java\0R100\0src/A.java\0src/B.java\0"
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=output
        )

        changes = service.list_changed_files(
            Path("/fake/repo"), GitCommit("bbb", "aaa")
        )

    assert [(item.status, item.previous_path, item.path) for item in changes] == [
        ("M", None, "src/App.java"),
        ("D", None, "src/Old.java"),
        ("R", "src/A.java", "src/B.java"),
    ]


def test_reads_files_from_git_objects(service):
    with patch("app.services.git_clone.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"class App {}"
        )

        content = service.read_file_at_commit(Path("/fake/repo"), "abc", "src/App.java")

    assert content == b"class App {}"
