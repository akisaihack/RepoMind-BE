"""Orchestrate the end-to-end repository analysis pipeline."""

import logging
from uuid import UUID

from app.repositories.repository import RepositoryStore
from app.services.chunk_import import ChunkImportService
from app.services.code_graph_import import CodeGraphImportService
from app.services.git_clone import GitCloneService
from app.services.github_history_import import GitHubHistoryImportService

logger = logging.getLogger(__name__)


class AnalysisPipelineService:
    """Coordinates git clone, history import, code graph import, and chunking."""

    def __init__(
        self,
        git_clone_service: GitCloneService,
        history_import_service: GitHubHistoryImportService,
        code_graph_import_service: CodeGraphImportService,
        chunk_import_service: ChunkImportService,
        repository_store: RepositoryStore,
    ) -> None:
        self._git_clone = git_clone_service
        self._history_import = history_import_service
        self._code_graph_import = code_graph_import_service
        self._chunk_import = chunk_import_service
        self._repository_store = repository_store

    def run_pipeline(self, repository_id: UUID, repository_url: str, branch: str) -> None:
        """Run the full analysis pipeline and update the repository status.

        Args:
            repository_id: The UUID of the repository in the local RDB.
            repository_url: The GitHub URL to clone.
            branch: The branch to analyze.
        """
        logger.info(f"Starting analysis pipeline for repository {repository_id} ({repository_url})")

        try:
            # 1. Update status to indexing
            self._repository_store.transition_status(repository_id, "pending", "indexing")
            
            # 2. Fetch GitHub history first to get github_repository_id
            logger.info("Importing GitHub history...")
            history_result = self._history_import.import_history()
            github_repo_id = history_result.repository_id
            
            # 3. Clone the repository locally
            logger.info(f"Cloning {repository_url} (branch: {branch})...")
            with self._git_clone.clone(repository_url, branch) as repo_path:
                commit_hash = self._git_clone.get_commit_hash(repo_path)
                
                # 4. Import the code graph into Neo4j
                logger.info("Importing code graph...")
                self._code_graph_import.import_repository(
                    github_repository_id=github_repo_id,
                    repository_path=repo_path,
                )
                
                # 5. Import and embed chunks into pgvector
                logger.info("Importing and embedding code chunks...")
                self._chunk_import.import_repository(
                    github_repository_id=github_repo_id,
                    repository_path=repo_path,
                    commit_hash=commit_hash,
                )
                
            # 6. Update status to ready and save github details
            logger.info("Pipeline completed successfully.")
            repo = self._repository_store.get(repository_id)
            if repo:
                repo.github_repository_id = github_repo_id
                repo.latest_analyzed_sha = commit_hash
                self._repository_store.transition_status(repository_id, "indexing", "ready")
                
        except Exception as exc:
            logger.exception(f"Analysis pipeline failed for repository {repository_id}: {exc}")
            try:
                self._repository_store.transition_status(repository_id, "indexing", "failed")
            except Exception as transition_exc:
                logger.error(f"Failed to transition status to failed: {transition_exc}")
            raise

