"""Repository registration persistence tests."""

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.repository import Repository, RepositoryAnalysisStatus


def _repository(**overrides: object) -> Repository:
    values: dict[str, object] = {
        "repository_url": "https://github.com/example/repomind.git",
        "branch": "develop",
    }
    values.update(overrides)
    return Repository(**values)


def test_creates_repository_with_pending_status(app) -> None:
    with app.app_context():
        db.create_all()
        repository = _repository()
        db.session.add(repository)
        db.session.commit()

        assert repository.id is not None
        assert repository.analysis_status == RepositoryAnalysisStatus.PENDING.value
        assert repository.github_repository_id is None
        assert repository.latest_analyzed_sha is None


def test_rejects_duplicate_repository_url_and_branch(app) -> None:
    with app.app_context():
        db.create_all()
        db.session.add_all([_repository(), _repository()])

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("Repository URL and branch must be unique.")


def test_rejects_unknown_analysis_status(app) -> None:
    with app.app_context():
        db.create_all()
        db.session.add(_repository(analysis_status="unknown"))

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("Unknown analysis statuses must be rejected.")
