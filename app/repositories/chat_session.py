"""RDB access for repository-scoped chat sessions."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession


class ChatSessionNotFoundError(Exception):
    """Raised when an operation requires a chat session that does not exist."""


class ChatSessionPersistenceError(Exception):
    """Raised when a chat session cannot be persisted or queried."""


class ChatSessionStore:
    """Persist and retrieve chat sessions belonging to registered repositories."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, repository_id: UUID, title: str | None = None) -> ChatSession:
        values: dict[str, object] = {"repository_id": repository_id}
        if title is not None:
            values["title"] = title

        chat_session = ChatSession(**values)
        self._session.add(chat_session)

        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChatSessionPersistenceError("Failed to create chat session.") from exc

        return chat_session

    def get(self, session_id: UUID) -> ChatSession | None:
        try:
            return self._session.get(ChatSession, session_id)
        except SQLAlchemyError as exc:
            raise ChatSessionPersistenceError("Failed to retrieve chat session.") from exc

    def get_with_repository(self, session_id: UUID) -> ChatSession | None:
        """Return a chat session together with its registered repository."""
        statement = (
            select(ChatSession)
            .options(joinedload(ChatSession.repository))
            .where(ChatSession.id == session_id)
        )
        try:
            return self._session.scalar(statement)
        except SQLAlchemyError as exc:
            raise ChatSessionPersistenceError(
                "Failed to retrieve chat session with repository."
            ) from exc

    def list_by_repository(self, repository_id: UUID) -> list[ChatSession]:
        statement = (
            select(ChatSession)
            .where(ChatSession.repository_id == repository_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        )
        try:
            return list(self._session.scalars(statement))
        except SQLAlchemyError as exc:
            raise ChatSessionPersistenceError("Failed to list chat sessions.") from exc

    def update_title(self, session_id: UUID, *, title: str) -> ChatSession:
        chat_session = self.get(session_id)
        if chat_session is None:
            raise ChatSessionNotFoundError("Chat session not found.")

        chat_session.title = title
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChatSessionPersistenceError("Failed to update chat session.") from exc

        return chat_session

    def delete(self, session_id: UUID) -> bool:
        chat_session = self.get(session_id)
        if chat_session is None:
            return False

        try:
            self._session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
            self._session.delete(chat_session)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChatSessionPersistenceError("Failed to delete chat session.") from exc

        return True
