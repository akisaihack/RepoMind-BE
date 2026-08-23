"""Session management API endpoints."""

from dataclasses import asdict
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, request

from app.dtos.sessions import (
    ChatMessageInfo,
    MessageHistoryResponse,
    SessionCreateRequest,
    SessionResponse,
)
from app.errors import APIError
from app.extensions import db
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.repository import RepositoryAnalysisStatus
from app.repositories.chat_message import ChatMessagePersistenceError, ChatMessageStore
from app.repositories.chat_session import ChatSessionPersistenceError, ChatSessionStore
from app.repositories.repository import RepositoryPersistenceError, RepositoryStore
from app.responses import success_response

sessions_bp = Blueprint("sessions", __name__)


def _get_repository_store() -> RepositoryStore:
    return RepositoryStore(db.session)


def _get_chat_session_store() -> ChatSessionStore:
    return ChatSessionStore(db.session)


def _get_chat_message_store() -> ChatMessageStore:
    return ChatMessageStore(db.session)


def _parse_repository_id(value: object) -> UUID:
    if not isinstance(value, str):
        raise APIError("INVALID_REPOSITORY_ID", "repo_id must be a UUID.")

    try:
        return UUID(value)
    except ValueError as exc:
        raise APIError("INVALID_REPOSITORY_ID", "repo_id must be a UUID.") from exc


def _parse_title(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise APIError("INVALID_SESSION_TITLE", "title must be a string.")

    title = value.strip()
    if not title:
        raise APIError("INVALID_SESSION_TITLE", "title must not be empty.")
    if len(title) > 255:
        raise APIError("INVALID_SESSION_TITLE", "title must not exceed 255 characters.")
    return title


def _parse_session_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise APIError("INVALID_SESSION_ID", "session_id must be a UUID.") from exc


def _to_session_response(chat_session: ChatSession) -> SessionResponse:
    return SessionResponse(
        session_id=str(chat_session.id),
        repo_id=str(chat_session.repository_id),
        title=chat_session.title,
        created_at=chat_session.created_at.isoformat(),
        updated_at=chat_session.updated_at.isoformat(),
    )


def _to_chat_message_info(message: ChatMessage) -> ChatMessageInfo:
    return ChatMessageInfo(
        message_id=str(message.id),
        role=message.role,
        content=message.content,
        structured_answer=message.structured_answer,
        created_at=message.created_at.isoformat(),
    )


@sessions_bp.post("/")
def create_session():
    """Create a persisted chat session for an analysis-ready repository."""

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("INVALID_REQUEST", "A JSON object is required.")

    repository_id = _parse_repository_id(data.get("repo_id"))
    create_request = SessionCreateRequest(
        repo_id=str(repository_id),
        title=_parse_title(data.get("title")),
    )
    repository_store = _get_repository_store()

    try:
        repository = repository_store.get(repository_id)
    except RepositoryPersistenceError as exc:
        raise APIError(
            "REPOSITORY_RETRIEVAL_FAILED",
            "Repository details could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    if repository is None:
        raise APIError(
            "REPOSITORY_NOT_FOUND",
            "The requested repository does not exist.",
            status=HTTPStatus.NOT_FOUND,
        )
    if repository.analysis_status != RepositoryAnalysisStatus.READY.value:
        raise APIError(
            "REPOSITORY_NOT_READY",
            "Chat sessions can be created only after repository analysis is ready.",
            status=HTTPStatus.CONFLICT,
            details={"analysis_status": repository.analysis_status},
        )

    try:
        chat_session = _get_chat_session_store().create(
            repository_id=repository_id,
            title=create_request.title,
        )
    except ChatSessionPersistenceError as exc:
        raise APIError(
            "SESSION_PERSISTENCE_FAILED",
            "Chat session could not be created.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    return success_response(
        asdict(_to_session_response(chat_session)),
        status=HTTPStatus.CREATED,
    )


@sessions_bp.get("/<session_id>/messages")
def get_session_messages(session_id: str):
    """Return persisted chat messages for one existing session."""

    parsed_session_id = _parse_session_id(session_id)
    session_store = _get_chat_session_store()

    try:
        chat_session = session_store.get(parsed_session_id)
    except ChatSessionPersistenceError as exc:
        raise APIError(
            "SESSION_RETRIEVAL_FAILED",
            "Chat session details could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    if chat_session is None:
        raise APIError(
            "SESSION_NOT_FOUND",
            "The requested chat session does not exist.",
            status=HTTPStatus.NOT_FOUND,
        )

    try:
        messages = _get_chat_message_store().list_by_session(parsed_session_id)
    except ChatMessagePersistenceError as exc:
        raise APIError(
            "MESSAGE_RETRIEVAL_FAILED",
            "Chat messages could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    response_data = MessageHistoryResponse(
        session_id=str(chat_session.id),
        messages=[_to_chat_message_info(message) for message in messages],
    )
    return success_response(asdict(response_data))


@sessions_bp.delete("/<session_id>")
def delete_session(session_id: str):
    """Delete one chat session and all of its persisted messages."""

    parsed_session_id = _parse_session_id(session_id)

    try:
        deleted = _get_chat_session_store().delete(parsed_session_id)
    except ChatSessionPersistenceError as exc:
        raise APIError(
            "SESSION_DELETION_FAILED",
            "Chat session could not be deleted.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    if not deleted:
        raise APIError(
            "SESSION_NOT_FOUND",
            "The requested chat session does not exist.",
            status=HTTPStatus.NOT_FOUND,
        )

    return success_response({"session_id": str(parsed_session_id)})


@sessions_bp.get("/")
def list_sessions():
    """Return persisted chat sessions belonging to one repository."""

    repository_id = _parse_repository_id(request.args.get("repo_id"))
    repository_store = _get_repository_store()

    try:
        repository = repository_store.get(repository_id)
    except RepositoryPersistenceError as exc:
        raise APIError(
            "REPOSITORY_RETRIEVAL_FAILED",
            "Repository details could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    if repository is None:
        raise APIError(
            "REPOSITORY_NOT_FOUND",
            "The requested repository does not exist.",
            status=HTTPStatus.NOT_FOUND,
        )

    try:
        sessions = _get_chat_session_store().list_by_repository(repository_id)
    except ChatSessionPersistenceError as exc:
        raise APIError(
            "SESSION_RETRIEVAL_FAILED",
            "Chat sessions could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    return success_response(
        {"sessions": [asdict(_to_session_response(chat_session)) for chat_session in sessions]}
    )
