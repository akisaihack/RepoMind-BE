"""RDB access for messages persisted in chat sessions."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import ChatSession


class ChatMessageSessionNotFoundError(Exception):
    """Raised when a message is created for a chat session that does not exist."""


class InvalidChatMessageRoleError(ValueError):
    """Raised when a message role is not supported by the persistence model."""


class ChatMessagePersistenceError(Exception):
    """Raised when a chat message cannot be persisted or queried."""


class ChatMessageStore:
    """Persist and retrieve messages belonging to chat sessions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        session_id: UUID,
        role: ChatMessageRole | str,
        content: str,
        structured_answer: dict[str, Any] | None = None,
    ) -> ChatMessage:
        role_value = self._normalize_role(role)
        chat_session = self._get_session(session_id)
        if chat_session is None:
            raise ChatMessageSessionNotFoundError("Chat session not found.")

        message = ChatMessage(
            session_id=session_id,
            role=role_value,
            content=content,
            structured_answer=structured_answer,
        )
        chat_session.updated_at = datetime.now(UTC)
        self._session.add(message)

        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChatMessagePersistenceError("Failed to create chat message.") from exc

        return message

    def create_exchange(
        self,
        *,
        session_id: UUID,
        question: str,
        answer: str,
        structured_answer: dict[str, Any],
    ) -> tuple[ChatMessage, ChatMessage]:
        """Persist one user question and its assistant answer atomically."""

        chat_session = self._get_session(session_id)
        if chat_session is None:
            raise ChatMessageSessionNotFoundError("Chat session not found.")

        user_message = ChatMessage(
            session_id=session_id,
            role=ChatMessageRole.USER.value,
            content=question,
        )
        assistant_message = ChatMessage(
            session_id=session_id,
            role=ChatMessageRole.ASSISTANT.value,
            content=answer,
            structured_answer=structured_answer,
        )
        chat_session.updated_at = datetime.now(UTC)
        self._session.add_all([user_message, assistant_message])

        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChatMessagePersistenceError("Failed to create chat exchange.") from exc

        return user_message, assistant_message

    def get(self, message_id: UUID) -> ChatMessage | None:
        try:
            return self._session.get(ChatMessage, message_id)
        except SQLAlchemyError as exc:
            raise ChatMessagePersistenceError("Failed to retrieve chat message.") from exc

    def list_by_session(self, session_id: UUID) -> list[ChatMessage]:
        statement = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        try:
            return list(self._session.scalars(statement))
        except SQLAlchemyError as exc:
            raise ChatMessagePersistenceError("Failed to list chat messages.") from exc

    def delete(self, message_id: UUID) -> bool:
        message = self.get(message_id)
        if message is None:
            return False

        try:
            self._session.delete(message)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ChatMessagePersistenceError("Failed to delete chat message.") from exc

        return True

    def _get_session(self, session_id: UUID) -> ChatSession | None:
        try:
            return self._session.get(ChatSession, session_id)
        except SQLAlchemyError as exc:
            raise ChatMessagePersistenceError("Failed to retrieve chat session.") from exc

    @staticmethod
    def _normalize_role(role: ChatMessageRole | str) -> str:
        try:
            return ChatMessageRole(role).value
        except ValueError as exc:
            raise InvalidChatMessageRoleError(
                "role must be either 'user' or 'assistant'."
            ) from exc
