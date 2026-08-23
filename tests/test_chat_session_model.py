"""Persistence tests for repository-scoped chat sessions."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.chat_session import DEFAULT_CHAT_SESSION_TITLE, ChatSession
from app.models.repository import Repository


def _enable_foreign_keys() -> None:
    db.session.execute(text("PRAGMA foreign_keys = ON"))


def _repository() -> Repository:
    return Repository(
        repository_url="https://github.com/example/repomind.git",
        branch="main",
    )


def test_creates_session_with_default_title_and_repository_relationship(app) -> None:
    with app.app_context():
        repository = _repository()
        session = ChatSession(repository=repository)
        db.session.add(session)
        db.session.commit()

        assert session.id is not None
        assert session.repository_id == repository.id
        assert session.title == DEFAULT_CHAT_SESSION_TITLE
        assert session.created_at is not None
        assert session.updated_at is not None
        assert repository.chat_sessions == [session]


def test_rejects_session_for_missing_repository(app) -> None:
    with app.app_context():
        _enable_foreign_keys()
        session = ChatSession(repository_id=UUID("00000000-0000-0000-0000-000000000001"))
        db.session.add(session)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("A chat session must reference an existing repository.")
