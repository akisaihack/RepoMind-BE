"""Commit file-change relational persistence tests."""

from flask import Flask

from app.dtos.github import CommitDTO, CommitFileDTO
from app.extensions import db
from app.models.commit_file_change import CommitFileChange
from app.repositories.commit_file_change import CommitFileChangeRepository


def _commit(patch: str | None = "@@ -1,2 +1,3 @@") -> CommitDTO:
    return CommitDTO(
        sha="abc123",
        message="Change service",
        html_url="https://github.com/org/repo/commit/abc123",
        author_name="Developer",
        author_id=7,
        author_login="developer",
        authored_at="2026-08-01T00:00:00Z",
        committed_at="2026-08-01T00:00:00Z",
        parent_shas=("parent123",),
        files=(
            CommitFileDTO(
                filename="app/service.py",
                previous_filename="app/old_service.py",
                status="renamed",
                additions=3,
                deletions=2,
                changes=5,
                blob_url=None,
                raw_url=None,
                patch=patch,
            ),
        ),
    )


def test_upserts_file_change_and_replaces_hunks(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        repository = CommitFileChangeRepository(db.session)

        first_ids = repository.upsert_changes(100, (_commit(),))
        second_ids = repository.upsert_changes(100, (_commit("@@ -5 +5,2 @@"),))

        changes = db.session.query(CommitFileChange).all()
        assert len(changes) == 1
        assert first_ids == second_ids == {("abc123", "app/service.py"): changes[0].id}
        assert changes[0].previous_file_path == "app/old_service.py"
        assert changes[0].patch_status == "available"
        assert len(changes[0].hunks) == 1
        assert changes[0].hunks[0].new_start_line == 5


def test_marks_missing_patch_unavailable(app: Flask) -> None:
    with app.app_context():
        db.create_all()

        CommitFileChangeRepository(db.session).upsert_changes(100, (_commit(None),))

        change = db.session.query(CommitFileChange).one()
        assert change.patch_status == "unavailable"
        assert change.hunks == []
