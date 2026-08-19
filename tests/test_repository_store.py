import pytest
import uuid

from app.extensions import db
from app.repositories.repository import RepositoryStore, InvalidStateTransitionError, RepositoryPersistenceError

def test_transition_status_success(app):
    with app.app_context():
        db.create_all()
        store = RepositoryStore(db.session)
        repo = store.create(repository_url="https://github.com/owner/repo", branch="main")
        
        assert repo.analysis_status == "pending"
        
        # pending -> indexing
        updated_repo = store.transition_status(repo.id, "pending", "indexing")
        assert updated_repo.analysis_status == "indexing"
        
        # indexing -> ready
        updated_repo = store.transition_status(repo.id, "indexing", "ready")
        assert updated_repo.analysis_status == "ready"

def test_transition_status_invalid_transition(app):
    with app.app_context():
        db.create_all()
        store = RepositoryStore(db.session)
        repo = store.create(repository_url="https://github.com/owner/repo2", branch="main")
        
        with pytest.raises(InvalidStateTransitionError, match="Cannot transition status from 'pending' to 'ready'"):
            store.transition_status(repo.id, "pending", "ready")

def test_transition_status_wrong_current_status(app):
    with app.app_context():
        db.create_all()
        store = RepositoryStore(db.session)
        repo = store.create(repository_url="https://github.com/owner/repo3", branch="main")
        
        with pytest.raises(InvalidStateTransitionError, match="Repository is currently in 'pending' state"):
            store.transition_status(repo.id, "indexing", "ready")

def test_transition_status_not_found(app):
    with app.app_context():
        db.create_all()
        store = RepositoryStore(db.session)
        with pytest.raises(RepositoryPersistenceError, match="Repository not found"):
            store.transition_status(uuid.uuid4(), "pending", "indexing")
