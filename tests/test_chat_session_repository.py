"""RDB repository tests for persisted chat sessions."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models.repository import Repository
from app.repositories.chat_session import (
    ChatSessionNotFoundError,
    ChatSessionPersistenceError,
    ChatSessionStore,
)


def _repository(*, suffix: str) -> Repository:
    return Repository(
        repository_url=f"https://github.com/example/repomind-{suffix}.git",
        branch="main",
    )


def _enable_foreign_keys() -> None:
    db.session.execute(text("PRAGMA foreign_keys = ON"))


def test_creates_and_retrieves_chat_session(app) -> None:
    with app.app_context():
        repository = _repository(suffix="create")
        db.session.add(repository)
        db.session.commit()
        store = ChatSessionStore(db.session)

        created = store.create(repository_id=repository.id, title="로그인 흐름")

        assert created.repository_id == repository.id
        assert created.title == "로그인 흐름"
        assert store.get(created.id) == created
        assert store.get(uuid4()) is None


def test_lists_only_sessions_for_requested_repository_in_recent_activity_order(app) -> None:
    with app.app_context():
        first_repository = _repository(suffix="first")
        second_repository = _repository(suffix="second")
        db.session.add_all([first_repository, second_repository])
        db.session.commit()
        store = ChatSessionStore(db.session)
        older = store.create(repository_id=first_repository.id, title="이전 세션")
        newer = store.create(repository_id=first_repository.id, title="최근 세션")
        other_repository_session = store.create(
            repository_id=second_repository.id,
            title="다른 레포지토리 세션",
        )
        newer.updated_at = newer.updated_at.replace(year=newer.updated_at.year + 1)
        db.session.commit()

        sessions = store.list_by_repository(first_repository.id)

        assert sessions == [newer, older]
        assert other_repository_session not in sessions


def test_updates_title_and_updated_at(app) -> None:
    with app.app_context():
        repository = _repository(suffix="update")
        db.session.add(repository)
        db.session.commit()
        store = ChatSessionStore(db.session)
        chat_session = store.create(repository_id=repository.id, title="초기 제목")
        previous_updated_at = chat_session.updated_at

        updated = store.update_title(chat_session.id, title="변경된 제목")

        assert updated.title == "변경된 제목"
        assert updated.updated_at >= previous_updated_at
        with pytest.raises(ChatSessionNotFoundError, match="Chat session not found"):
            store.update_title(uuid4(), title="없는 세션")


def test_deletes_session_and_returns_false_for_missing_session(app) -> None:
    with app.app_context():
        repository = _repository(suffix="delete")
        db.session.add(repository)
        db.session.commit()
        store = ChatSessionStore(db.session)
        chat_session = store.create(repository_id=repository.id)

        assert store.delete(chat_session.id) is True
        assert store.get(chat_session.id) is None
        assert store.delete(chat_session.id) is False


def test_rolls_back_after_failed_create(app) -> None:
    with app.app_context():
        _enable_foreign_keys()
        store = ChatSessionStore(db.session)

        with pytest.raises(ChatSessionPersistenceError, match="Failed to create chat session"):
            store.create(repository_id=UUID("00000000-0000-0000-0000-000000000001"))

        repository = _repository(suffix="rollback")
        db.session.add(repository)
        db.session.commit()
        created = store.create(repository_id=repository.id)

        assert created.repository_id == repository.id
