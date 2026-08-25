"""Git repository clone service for analysis jobs."""

import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class GitCloneError(Exception):
    """Raised when repository clone or commit hash retrieval fails."""


class GitHistoryLimitError(GitCloneError):
    """Raised when repository history exceeds the configured safe limit."""


@dataclass(frozen=True, slots=True)
class GitCommit:
    sha: str
    parent_sha: str | None


@dataclass(frozen=True, slots=True)
class GitFileChange:
    status: str
    path: str
    previous_path: str | None = None


class GitCloneService:
    """Service to safely clone a remote Git repository to a temporary local path."""

    @contextmanager
    def clone(self, repository_url: str, branch: str) -> Generator[Path, None, None]:
        """Clone a repository into a temporary directory and yield its path.
        
        Clones one branch with its full first-parent history for MethodVersion indexing.
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
                        "--branch",
                        branch,
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

    def list_first_parent_commits(
        self,
        repository_path: Path,
        *,
        after_sha: str | None = None,
        max_commits: int = 2_000,
    ) -> list[GitCommit]:
        if max_commits <= 0:
            raise ValueError("max_commits must be positive.")
        output = self._run_text(
            repository_path,
            ["git", "rev-list", "--first-parent", "--reverse", "--parents", "HEAD"],
        )
        commits: list[GitCommit] = []
        found_checkpoint = after_sha is None
        for line in output.splitlines():
            parts = line.split()
            if not parts:
                continue
            sha = parts[0]
            parent_sha = parts[1] if len(parts) > 1 else None
            if not found_checkpoint:
                if sha == after_sha:
                    found_checkpoint = True
                continue
            if sha == after_sha:
                continue
            commits.append(GitCommit(sha=sha, parent_sha=parent_sha))
        if after_sha is not None and not found_checkpoint:
            raise GitCloneError("History checkpoint is not on the cloned branch.")
        if len(commits) > max_commits:
            raise GitHistoryLimitError(
                f"Commit history exceeds configured limit ({max_commits})."
            )
        return commits

    def list_changed_files(
        self,
        repository_path: Path,
        commit: GitCommit,
    ) -> list[GitFileChange]:
        if commit.parent_sha is None:
            command = [
                "git",
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-status",
                "-r",
                "-M",
                "-z",
                commit.sha,
            ]
        else:
            command = [
                "git",
                "diff",
                "--name-status",
                "-M",
                "-z",
                commit.parent_sha,
                commit.sha,
            ]
        fields = self._run_bytes(repository_path, command).decode(
            "utf-8", errors="surrogateescape"
        ).split("\0")
        changes: list[GitFileChange] = []
        index = 0
        while index < len(fields) and fields[index]:
            status_token = fields[index]
            index += 1
            status = status_token[0]
            if status in {"R", "C"}:
                previous_path, path = fields[index], fields[index + 1]
                index += 2
                changes.append(
                    GitFileChange(status=status, path=path, previous_path=previous_path)
                )
            else:
                path = fields[index]
                index += 1
                changes.append(GitFileChange(status=status, path=path))
        return changes

    def list_files_at_commit(self, repository_path: Path, commit_sha: str) -> list[str]:
        output = self._run_bytes(
            repository_path,
            ["git", "ls-tree", "-r", "--name-only", "-z", commit_sha],
        )
        return [
            path
            for path in output.decode("utf-8", errors="surrogateescape").split("\0")
            if path
        ]

    def read_file_at_commit(
        self,
        repository_path: Path,
        commit_sha: str,
        path: str,
    ) -> bytes:
        return self._run_bytes(
            repository_path,
            ["git", "show", f"{commit_sha}:{path}"],
        )

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

    @staticmethod
    def _run_text(repository_path: Path, command: list[str]) -> str:
        try:
            result = subprocess.run(
                command,
                cwd=repository_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            raise GitCloneError(f"Git history command failed: {exc.stderr}") from exc

    @staticmethod
    def _run_bytes(repository_path: Path, command: list[str]) -> bytes:
        try:
            result = subprocess.run(
                command,
                cwd=repository_path,
                check=True,
                capture_output=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            stderr = (
                exc.stderr.decode(errors="replace")
                if isinstance(exc.stderr, bytes)
                else exc.stderr
            )
            raise GitCloneError(f"Git history command failed: {stderr}") from exc


__all__ = [
    "GitCloneError",
    "GitCloneService",
    "GitCommit",
    "GitFileChange",
    "GitHistoryLimitError",
]
