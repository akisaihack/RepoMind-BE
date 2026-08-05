"""PostgreSQL persistence for Commit file changes and patch hunks."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.dtos.github import CommitDTO
from app.models.commit_file_change import CommitFileChange, CommitFileChangeHunk
from app.parsers.patch import parse_patch_hunks


class FileChangePersistenceError(Exception):
    """Raised when file-change persistence fails."""


class CommitFileChangeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_changes(
        self,
        github_repository_id: int,
        commits: tuple[CommitDTO, ...],
    ) -> dict[tuple[str, str], int]:
        """Persist every detailed Commit file and return its stable database ID."""
        identifiers: dict[tuple[str, str], int] = {}
        try:
            for commit in commits:
                for file in commit.files:
                    change = self._find(github_repository_id, commit.sha, file.filename)
                    if change is None:
                        change = CommitFileChange(
                            github_repository_id=github_repository_id,
                            commit_sha=commit.sha,
                            file_path=file.filename,
                            status=file.status,
                            patch_status=_patch_status(file.patch),
                        )
                        self._session.add(change)

                    change.previous_file_path = file.previous_filename
                    change.status = file.status
                    change.additions = file.additions
                    change.deletions = file.deletions
                    change.changes = file.changes
                    change.patch = file.patch
                    change.patch_source = "github"
                    change.patch_status = _patch_status(file.patch)
                    change.updated_at = datetime.now(UTC)
                    change.hunks.clear()
                    change.hunks.extend(
                        CommitFileChangeHunk(
                            old_start_line=hunk.old_start_line,
                            old_line_count=hunk.old_line_count,
                            new_start_line=hunk.new_start_line,
                            new_line_count=hunk.new_line_count,
                        )
                        for hunk in parse_patch_hunks(file.patch)
                    )
                    self._session.flush()
                    identifiers[(commit.sha, file.filename)] = change.id

            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise FileChangePersistenceError("Failed to persist Commit file changes.") from exc

        return identifiers

    def _find(
        self,
        github_repository_id: int,
        commit_sha: str,
        file_path: str,
    ) -> CommitFileChange | None:
        statement = select(CommitFileChange).where(
            CommitFileChange.github_repository_id == github_repository_id,
            CommitFileChange.commit_sha == commit_sha,
            CommitFileChange.file_path == file_path,
        )
        return self._session.scalars(statement).one_or_none()


def _patch_status(patch: str | None) -> str:
    return "available" if patch is not None else "unavailable"
