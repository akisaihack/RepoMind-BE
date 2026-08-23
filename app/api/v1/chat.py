"""Chat query API backed by the repository Q&A service."""

from dataclasses import asdict
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request

from app.dtos.chat import ChatRequest
from app.dtos.question import QuestionKind
from app.errors import APIError
from app.extensions import db
from app.repositories.chat_message import (
    ChatMessagePersistenceError,
    ChatMessageSessionNotFoundError,
    ChatMessageStore,
)
from app.repositories.chat_session import ChatSessionPersistenceError, ChatSessionStore
from app.services.qa_service import (
    QAGitHubRepositoryIdMissingError,
    QARepositoryNotReadyError,
    QAService,
    QASessionNotFoundError,
)

chat_bp = Blueprint("chat", __name__)


def _get_chat_message_store() -> ChatMessageStore:
    return ChatMessageStore(db.session)


def _get_qa_service() -> QAService:
    return QAService(ChatSessionStore(db.session))


def _parse_session_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise APIError("INVALID_SESSION_ID", "session_id must be a UUID.") from exc


def _parse_question(value: object) -> str:
    if not isinstance(value, str):
        raise APIError("INVALID_QUESTION", "question must be a string.")

    question = value.strip()
    if not question:
        raise APIError("INVALID_QUESTION", "question must not be empty.")
    return question


@chat_bp.post("/sessions/<session_id>/chat")
def chat(session_id: str):
    """Answer one question using the session's analyzed repository context."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("INVALID_REQUEST", "A JSON object is required.")

    parsed_session_id = _parse_session_id(session_id)
    raw_question_kind = data.get("question_kind")
    try:
        question_kind = QuestionKind(raw_question_kind) if raw_question_kind is not None else None
    except ValueError as exc:
        raise APIError(
            "INVALID_QUESTION_KIND",
            f"question_kind must be one of: {', '.join(QuestionKind)}.",
        ) from exc

    request_dto = ChatRequest(
        question=_parse_question(data.get("question")),
        question_kind=question_kind,
    )
    try:
        response_data = _get_qa_service().ask(parsed_session_id, request_dto)
    except QASessionNotFoundError as exc:
        raise APIError(
            "SESSION_NOT_FOUND",
            "The requested chat session does not exist.",
            status=HTTPStatus.NOT_FOUND,
        ) from exc
    except QARepositoryNotReadyError as exc:
        raise APIError(
            "REPOSITORY_NOT_READY",
            "Repository analysis must be ready before asking questions.",
            status=HTTPStatus.CONFLICT,
        ) from exc
    except QAGitHubRepositoryIdMissingError as exc:
        raise APIError(
            "REPOSITORY_NOT_ANALYZED",
            "Repository analysis metadata is incomplete.",
            status=HTTPStatus.CONFLICT,
        ) from exc
    except ChatSessionPersistenceError as exc:
        raise APIError(
            "SESSION_RETRIEVAL_FAILED",
            "Chat session details could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc
    except APIError:
        raise
    except Exception as exc:
        current_app.logger.exception("Q&A pipeline failed", exc_info=exc)
        raise APIError(
            "QA_PIPELINE_FAILED",
            "The question could not be answered at this time.",
            status=HTTPStatus.BAD_GATEWAY,
        ) from exc

    serialized_response = asdict(response_data)
    try:
        _get_chat_message_store().create_exchange(
            session_id=parsed_session_id,
            question=request_dto.question,
            answer=response_data.summary,
            structured_answer=serialized_response,
        )
    except ChatMessageSessionNotFoundError as exc:
        raise APIError(
            "SESSION_NOT_FOUND",
            "The requested chat session does not exist.",
            status=HTTPStatus.NOT_FOUND,
        ) from exc
    except ChatMessagePersistenceError as exc:
        raise APIError(
            "MESSAGE_PERSISTENCE_FAILED",
            "Chat messages could not be saved.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    return jsonify({"success": True, "data": serialized_response}), HTTPStatus.OK
