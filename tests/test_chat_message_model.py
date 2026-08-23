"""Persistence tests for chat messages and their deletion policy."""

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import ChatSession
from app.models.repository import Repository


def _enable_foreign_keys() -> None:
    db.session.execute(text("PRAGMA foreign_keys = ON"))


def _session() -> ChatSession:
    repository = Repository(
        repository_url="https://github.com/example/repomind.git",
        branch="main",
    )
    return ChatSession(repository=repository, title="가입 흐름")


def test_persists_assistant_structured_answer(app) -> None:
    with app.app_context():
        session = _session()
        answer = {"summary": "가입 흐름입니다.", "claims": [{"id": "claim-1"}]}
        message = ChatMessage(
            session=session,
            role=ChatMessageRole.ASSISTANT.value,
            content="가입 흐름을 설명합니다.",
            structured_answer=answer,
        )
        db.session.add(message)
        db.session.commit()
        db.session.expire_all()

        persisted_message = db.session.get(ChatMessage, message.id)
        assert persisted_message is not None
        assert persisted_message.structured_answer == answer
        assert persisted_message.created_at is not None


def test_rejects_unknown_message_role(app) -> None:
    with app.app_context():
        session = _session()
        db.session.add(session)
        db.session.commit()
        db.session.add(
            ChatMessage(
                session_id=session.id,
                role="system",
                content="지원하지 않는 역할",
            )
        )

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("Only user and assistant message roles are supported.")


def test_deleting_repository_cascades_to_sessions_and_messages(app) -> None:
    with app.app_context():
        _enable_foreign_keys()
        session = _session()
        message = ChatMessage(
            session=session,
            role=ChatMessageRole.USER.value,
            content="가입은 어떻게 하나요?",
        )
        db.session.add(message)
        db.session.commit()

        repository_id = session.repository_id
        session_id = session.id
        message_id = message.id
        repository = db.session.get(Repository, repository_id)
        assert repository is not None
        db.session.delete(repository)
        db.session.commit()

        assert db.session.get(ChatSession, session_id) is None
        assert db.session.get(ChatMessage, message_id) is None
        assert db.session.scalars(select(ChatSession)).all() == []
