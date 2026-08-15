"""In-Memory repository store for testing and early development without RDB."""

from uuid import UUID, uuid4
from datetime import UTC, datetime
from typing import Dict, List

from app.models.repository import RepositoryAnalysisStatus
from app.repositories.repository import DuplicateRepositoryError


class InMemoryRepositoryStore:
    """Persist and retrieve registered repositories in memory."""

    def __init__(self) -> None:
        self._repositories: Dict[UUID, dict] = {}

    def create(self, *, repository_url: str, branch: str) -> dict:
        for repo in self._repositories.values():
            if repo["repository_url"] == repository_url and repo["branch"] == branch:
                raise DuplicateRepositoryError()

        repo_id = uuid4()
        now = datetime.now(UTC)
        repo_data = {
            "id": repo_id,
            "repository_url": repository_url,
            "branch": branch,
            "github_repository_id": None,
            "latest_analyzed_sha": None,
            "analysis_status": RepositoryAnalysisStatus.PENDING.value,
            "created_at": now,
            "updated_at": now,
        }
        
        self._repositories[repo_id] = repo_data
        return repo_data

    def get(self, repository_id: UUID) -> dict | None:
        return self._repositories.get(repository_id)

    def list(self) -> List[dict]:
        return sorted(
            list(self._repositories.values()),
            key=lambda x: x["updated_at"],
            reverse=True
        )

# Global singleton for in-memory persistence during the app lifecycle
_memory_store = InMemoryRepositoryStore()

def get_memory_store() -> InMemoryRepositoryStore:
    return _memory_store
