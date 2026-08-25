"""Orchestrate the end-to-end repository analysis pipeline."""

import logging
from time import monotonic
from uuid import UUID

from app.repositories.repository import RepositoryStore
from app.services.chunk_import import ChunkImportService
from app.services.code_graph_import import CodeGraphImportService
from app.services.git_clone import GitCloneService
from app.services.github_history_import import GitHubHistoryImportService
from app.services.method_history_index import MethodHistoryIndexer

logger = logging.getLogger(__name__)


class AnalysisPipelineService:
    """Coordinates git clone, history import, code graph import, and chunking."""

    def __init__(
        self,
        git_clone_service: GitCloneService,
        history_import_service: GitHubHistoryImportService,
        code_graph_import_service: CodeGraphImportService,
        method_history_indexer: MethodHistoryIndexer,
        chunk_import_service: ChunkImportService,
        repository_store: RepositoryStore,
    ) -> None:
        self._git_clone = git_clone_service
        self._history_import = history_import_service
        self._code_graph_import = code_graph_import_service
        self._method_history_indexer = method_history_indexer
        self._chunk_import = chunk_import_service
        self._repository_store = repository_store

    def run_pipeline(self, repository_id: UUID, repository_url: str, branch: str) -> None:
        """Run the full analysis pipeline and update the repository status.

        Args:
            repository_id: The UUID of the repository in the local RDB.
            repository_url: The GitHub URL to clone.
            branch: The branch to analyze.
        """
        pipeline_started_at = monotonic()
        logger.info(
            "저장소 분석을 시작합니다. 저장소 ID=%s, 브랜치=%s, URL=%s",
            repository_id,
            branch,
            repository_url,
        )

        try:
            # 1. Update status to indexing
            self._repository_store.transition_status(repository_id, "pending", "indexing")
            
            # 2. Fetch GitHub history first to get github_repository_id
            stage_started_at = monotonic()
            logger.info("[1/5] GitHub 개발 이력 수집을 시작합니다. 브랜치=%s", branch)
            history_result = self._history_import.import_history(branch)
            github_repo_id = history_result.repository_id
            logger.info(
                "[1/5] GitHub 개발 이력 수집을 완료했습니다. 소요 시간=%.2f초, "
                "커밋=%s개, 변경 파일=%s개, 이슈=%s개, PR=%s개",
                monotonic() - stage_started_at,
                history_result.commits,
                history_result.file_changes,
                history_result.issues,
                history_result.pull_requests,
            )
            
            # 3. Clone the repository locally
            stage_started_at = monotonic()
            logger.info("[2/5] Git 저장소 복제를 시작합니다. 브랜치=%s", branch)
            with self._git_clone.clone(repository_url, branch) as repo_path:
                commit_hash = self._git_clone.get_commit_hash(repo_path)
                logger.info(
                    "[2/5] Git 저장소 복제를 완료했습니다. 소요 시간=%.2f초, HEAD=%s",
                    monotonic() - stage_started_at,
                    commit_hash,
                )

                repo = self._repository_store.get(repository_id)
                history_checkpoint = repo.history_indexed_sha if repo else None

                # Build historical MethodVersions before replacing the HEAD snapshot.
                stage_started_at = monotonic()
                logger.info(
                    "[3/5] 메서드 전체 이력 인덱싱을 시작합니다. 이전 체크포인트=%s",
                    history_checkpoint or "none",
                )
                history_index_result = self._method_history_indexer.index(
                    github_repository_id=github_repo_id,
                    repository_path=repo_path,
                    after_sha=history_checkpoint,
                )
                logger.info(
                    "[3/5] 메서드 전체 이력 인덱싱을 완료했습니다. 소요 시간=%.2f초, "
                    "커밋=%s개, 변경 파일=%s개, 버전=%s개, 삭제=%s개",
                    monotonic() - stage_started_at,
                    history_index_result.commits,
                    history_index_result.changed_files,
                    history_index_result.versions,
                    history_index_result.deletions,
                )
                
                # 4. Import the code graph into Neo4j
                stage_started_at = monotonic()
                logger.info("[4/5] 최신 코드 그래프 생성을 시작합니다.")
                code_graph_result = self._code_graph_import.import_repository(
                    github_repository_id=github_repo_id,
                    repository_path=repo_path,
                    commit_hash=commit_hash,
                    persist_version_history=False,
                    mark_missing_deleted=False,
                )
                logger.info(
                    "[4/5] 최신 코드 그래프 생성을 완료했습니다. 소요 시간=%.2f초, "
                    "파일=%s개, 메서드=%s개, 관계=%s개",
                    monotonic() - stage_started_at,
                    code_graph_result.files,
                    code_graph_result.methods,
                    code_graph_result.relationships,
                )
                
                # 5. Import and embed chunks into pgvector
                stage_started_at = monotonic()
                logger.info("[5/5] 코드 청크 생성 및 임베딩을 시작합니다.")
                chunk_result = self._chunk_import.import_repository(
                    github_repository_id=github_repo_id,
                    repository_path=repo_path,
                    commit_hash=commit_hash,
                )
                logger.info(
                    "[5/5] 코드 청크 생성 및 임베딩을 완료했습니다. 소요 시간=%.2f초, "
                    "파일=%s개, 청크=%s개",
                    monotonic() - stage_started_at,
                    chunk_result.files,
                    chunk_result.chunks,
                )
                
            # 6. Update status to ready and save github details
            repo = self._repository_store.get(repository_id)
            if repo:
                repo.github_repository_id = github_repo_id
                repo.latest_analyzed_sha = commit_hash
                repo.history_indexed_sha = history_index_result.last_commit_sha
                self._repository_store.transition_status(repository_id, "indexing", "ready")
            logger.info(
                "저장소 분석을 완료했습니다. 저장소 ID=%s, 전체 소요 시간=%.2f초",
                repository_id,
                monotonic() - pipeline_started_at,
            )
                
        except Exception as exc:
            logger.exception(
                "저장소 분석에 실패했습니다. 저장소 ID=%s, 소요 시간=%.2f초, 오류=%s",
                repository_id,
                monotonic() - pipeline_started_at,
                exc,
            )
            try:
                self._repository_store.transition_status(repository_id, "indexing", "failed")
            except Exception as transition_exc:
                logger.error("분석 상태를 failed로 변경하지 못했습니다. 오류=%s", transition_exc)
            raise
