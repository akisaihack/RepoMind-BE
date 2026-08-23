"""Opt-in PostgreSQL validation for persisted chat sessions and messages."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.chat_session import ChatSession
from app.models.repository import Repository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to use local PostgreSQL",
    ),
]


def test_chat_migration_creates_persistence_contract() -> None:
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)

        assert {"chat_sessions", "chat_messages"}.issubset(inspector.get_table_names())
        assert _foreign_key(inspector, "chat_sessions", "repositories")["options"][
            "ondelete"
        ].upper() == "CASCADE"
        assert _foreign_key(inspector, "chat_messages", "chat_sessions")["options"][
            "ondelete"
        ].upper() == "CASCADE"
        assert {
            "ix_chat_sessions_repository_id_updated_at",
        }.issubset({index["name"] for index in inspector.get_indexes("chat_sessions")})
        assert {
            "ix_chat_messages_session_id_created_at",
        }.issubset({index["name"] for index in inspector.get_indexes("chat_messages")})
        assert "ck_chat_messages_role" in {
            constraint["name"] for constraint in inspector.get_check_constraints("chat_messages")
        }


def test_repository_delete_cascades_persisted_chat_data() -> None:
    app = create_app()
    repository_id: UUID | None = None

    with app.app_context():
        try:
            repository = Repository(
                repository_url=f"https://github.com/repomind/chat-persistence-{uuid4()}.git",
                branch="main",
            )
            chat_session = ChatSession(repository=repository, title="통합 테스트 대화")
            message = ChatMessage(
                session=chat_session,
                role=ChatMessageRole.ASSISTANT.value,
                content="구조화된 답변입니다.",
                structured_answer={"summary": "통합 테스트 응답"},
            )
            db.session.add(message)
            db.session.commit()

            repository_id = repository.id
            session_id = chat_session.id
            message_id = message.id
            db.session.execute(
                text("DELETE FROM repositories WHERE id = :repository_id"),
                {"repository_id": repository_id},
            )
            db.session.commit()
            db.session.expire_all()

            assert db.session.get(ChatSession, session_id) is None
            assert db.session.get(ChatMessage, message_id) is None
        finally:
            if repository_id is not None:
                db.session.execute(
                    text("DELETE FROM repositories WHERE id = :repository_id"),
                    {"repository_id": repository_id},
                )
                db.session.commit()


def _foreign_key(inspector: object, table_name: str, referred_table: str) -> dict[str, object]:
    foreign_keys = inspector.get_foreign_keys(table_name)  # type: ignore[attr-defined]
    return next(
        foreign_key
        for foreign_key in foreign_keys
        if foreign_key["referred_table"] == referred_table
    )
