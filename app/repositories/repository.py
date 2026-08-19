"""RDB access for registered source repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.repository import Repository


class DuplicateRepositoryError(Exception):
    """Raised when the same repository URL and branch are already registered."""


class InvalidStateTransitionError(Exception):
    """Raised when an invalid status transition is requested."""


class RepositoryPersistenceError(Exception):
    """Raised when a repository cannot be persisted or queried."""


class RepositoryStore:
    """Persist and retrieve registered repositories."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, repository_url: str, branch: str) -> Repository:
        repository = Repository(repository_url=repository_url, branch=branch)
        self._session.add(repository)

        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateRepositoryError from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise RepositoryPersistenceError("Failed to create repository.") from exc

        return repository

    def get(self, repository_id: UUID) -> Repository | None:
        try:
            return self._session.get(Repository, repository_id)
        except SQLAlchemyError as exc:
            raise RepositoryPersistenceError("Failed to retrieve repository.") from exc

    def delete(self, repository_id: UUID) -> None:
        repository = self.get(repository_id)
        if repository:
            try:
                self._session.delete(repository)
                self._session.commit()
            except SQLAlchemyError as exc:
                self._session.rollback()
                raise RepositoryPersistenceError("Failed to delete repository.") from exc

    def list(self) -> list[Repository]:
        statement = select(Repository).order_by(Repository.updated_at.desc())
        try:
            return list(self._session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryPersistenceError("Failed to list repositories.") from exc

    def transition_status(
        self, repository_id: UUID, from_status: str, to_status: str
    ) -> Repository:
        valid_transitions = {
            ("pending", "indexing"),
            ("indexing", "ready"),
            ("indexing", "failed"),
            ("failed", "pending"),
            ("ready", "pending"),
        }

        if (from_status, to_status) not in valid_transitions:
            raise InvalidStateTransitionError(
                f"Cannot transition status from '{from_status}' to '{to_status}'."
            )

        repository = self.get(repository_id)
        if repository is None:
            raise RepositoryPersistenceError("Repository not found.")

        if repository.analysis_status != from_status:
            raise InvalidStateTransitionError(
                f"Repository is currently in '{repository.analysis_status}' state, "
                f"expected '{from_status}'."
            )

        repository.analysis_status = to_status
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise RepositoryPersistenceError("Failed to transition repository status.") from exc

        return repository

