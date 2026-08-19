import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.git_clone import GitCloneError, GitCloneService


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
