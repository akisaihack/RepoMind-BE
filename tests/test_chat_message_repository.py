"""RDB repository tests for messages persisted in chat sessions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.extensions import db
from app.models.chat_message import ChatMessageRole
from app.models.chat_session import ChatSession
from app.models.repository import Repository
from app.repositories.chat_message import (
    ChatMessagePersistenceError,
    ChatMessageSessionNotFoundError,
    ChatMessageStore,
    InvalidChatMessageRoleError,
)


def _chat_session(*, suffix: str) -> ChatSession:
    repository = Repository(
        repository_url=f"https://github.com/example/repomind-{suffix}.git",
        branch="main",
    )
    return ChatSession(repository=repository, title="회원 가입 흐름")


def test_creates_user_and_assistant_messages_with_structured_answer(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="create")
        db.session.add(chat_session)
        db.session.commit()
        previous_updated_at = chat_session.updated_at
        store = ChatMessageStore(db.session)

        user_message = store.create(
            session_id=chat_session.id,
            role=ChatMessageRole.USER,
            content="가입 흐름을 알려줘.",
        )
        assistant_answer = {"summary": "가입 흐름입니다.", "claims": [{"id": "claim-1"}]}
        assistant_message = store.create(
            session_id=chat_session.id,
            role="assistant",
            content="가입 컨트롤러에서 시작합니다.",
            structured_answer=assistant_answer,
        )
        db.session.refresh(chat_session)

        assert user_message.structured_answer is None
        assert assistant_message.structured_answer == assistant_answer
        assert chat_session.updated_at >= previous_updated_at


def test_exchange_always_orders_user_message_before_assistant_message(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="exchange-order")
        db.session.add(chat_session)
        db.session.commit()
        store = ChatMessageStore(db.session)

        user_message, assistant_message = store.create_exchange(
            session_id=chat_session.id,
            question="질문",
            answer="답변",
            structured_answer={"summary": "답변"},
        )

        assert user_message.created_at < assistant_message.created_at
        assert store.list_by_session(chat_session.id) == [user_message, assistant_message]


def test_lists_messages_in_creation_order_within_session_only(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="history")
        other_chat_session = _chat_session(suffix="other")
        db.session.add_all([chat_session, other_chat_session])
        db.session.commit()
        store = ChatMessageStore(db.session)
        oldest = store.create(
            session_id=chat_session.id,
            role="user",
            content="첫 번째 질문",
        )
        newest = store.create(
            session_id=chat_session.id,
            role="assistant",
            content="첫 번째 답변",
        )
        store.create(
            session_id=other_chat_session.id,
            role="user",
            content="다른 세션 질문",
        )
        oldest.created_at = datetime.now(UTC) - timedelta(minutes=1)
        newest.created_at = datetime.now(UTC)
        db.session.commit()

        messages = store.list_by_session(chat_session.id)

        assert messages == [oldest, newest]


def test_rejects_unknown_role_and_unknown_session(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="validation")
        db.session.add(chat_session)
        db.session.commit()
        store = ChatMessageStore(db.session)

        with pytest.raises(InvalidChatMessageRoleError, match="user.*assistant"):
            store.create(session_id=chat_session.id, role="system", content="지원하지 않는 역할")
        with pytest.raises(ChatMessageSessionNotFoundError, match="Chat session not found"):
            store.create(session_id=uuid4(), role="user", content="없는 세션 질문")


def test_deletes_message_and_returns_false_for_missing_message(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="delete")
        db.session.add(chat_session)
        db.session.commit()
        store = ChatMessageStore(db.session)
        message = store.create(
            session_id=chat_session.id,
            role="user",
            content="삭제할 질문",
        )

        assert store.delete(message.id) is True
        assert store.get(message.id) is None
        assert store.delete(message.id) is False


def test_rolls_back_after_failed_message_create(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="rollback")
        db.session.add(chat_session)
        db.session.commit()
        store = ChatMessageStore(db.session)

        with pytest.raises(ChatMessagePersistenceError, match="Failed to create chat message"):
            store.create(
                session_id=chat_session.id,
                role="assistant",
                content="직렬화할 수 없는 답변",
                structured_answer={"invalid": {"set-is-not-json"}},
            )

        created = store.create(
            session_id=chat_session.id,
            role="user",
            content="rollback 이후에도 저장 가능",
        )

        assert created.session_id == chat_session.id
