"""Git repository clone service for analysis jobs."""

import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class GitCloneError(Exception):
    """Raised when repository clone or commit hash retrieval fails."""


class GitCloneService:
    """Service to safely clone a remote Git repository to a temporary local path."""

    @contextmanager
    def clone(self, repository_url: str, branch: str) -> Generator[Path, None, None]:
        """Clone a repository into a temporary directory and yield its path.
        
        Uses --depth 1 and --single-branch to optimize clone size.
        The temporary directory is automatically cleaned up when the context exits.
        
        Args:
            repository_url: The HTTPS or SSH URL of the Git repository.
            branch: The target branch to clone.
            
        Yields:
            The Path to the cloned local repository.
            
        Raises:
            GitCloneError: If the clone operation fails.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth", "1",
                        "--branch", branch,
                        "--single-branch",
                        repository_url,
                        ".",
                    ],
                    cwd=temp_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise GitCloneError(f"Failed to clone repository: {exc.stderr}") from exc

            yield temp_path

    def get_commit_hash(self, repository_path: Path) -> str:
        """Get the HEAD commit hash of a local Git checkout.
        
        Args:
            repository_path: The local repository Path.
            
        Returns:
            The 40-character SHA-1 commit hash.
            
        Raises:
            GitCloneError: If the git command fails.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository_path,
                check=True,
                capture_output=True,
                text=True,
            )
            commit_hash = result.stdout.strip()
            if not commit_hash:
                raise GitCloneError("Git rev-parse returned empty output.")
            return commit_hash
        except subprocess.CalledProcessError as exc:
            raise GitCloneError(f"Failed to get commit hash: {exc.stderr}") from exc
