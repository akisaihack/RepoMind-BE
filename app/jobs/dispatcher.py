import logging
from abc import ABC, abstractmethod
from time import monotonic

from app.dtos.analysis import AnalysisRequest

logger = logging.getLogger(__name__)


class AnalysisJobDispatcher(ABC):
    """Interface for dispatching background analysis jobs."""

    @abstractmethod
    def dispatch(self, request: AnalysisRequest) -> None:
        """Dispatch a repository analysis job.
        
        Args:
            request: The analysis request containing repository details.
            
        Raises:
            Exception: If the job could not be dispatched.
        """
        pass


class NoOpAnalysisJobDispatcher(AnalysisJobDispatcher):
    """A dispatcher that just logs the request instead of actually running it.
    Useful for local development before the actual task queue is integrated.
    """

    def dispatch(self, request: AnalysisRequest) -> None:
        logger.info(
            "분석 요청을 기록했습니다. URL=%s, 브랜치=%s, 저장소 ID=%s",
            request.repository_url,
            request.branch,
            request.repository_id,
        )


class ThreadAnalysisJobDispatcher(AnalysisJobDispatcher):
    """Executes the analysis pipeline asynchronously in a background thread."""

    def __init__(self, app) -> None:
        """Initialize with the Flask application to push context in threads."""
        self._app = app

    def dispatch(self, request: AnalysisRequest) -> None:
        import threading
        
        thread = threading.Thread(
            target=self._run_job,
            args=(request,),
            name=f"AnalysisJob-{request.repository_id}",
            daemon=True,
        )
        thread.start()
        logger.info(
            "백그라운드 분석 작업을 생성했습니다. 저장소 ID=%s, URL=%s",
            request.repository_id,
            request.repository_url,
        )

    def _run_job(self, request: AnalysisRequest) -> None:
        """Run the actual pipeline inside an application context."""
        from app.extensions import db
        from app.factories.pipeline import create_analysis_pipeline

        with self._app.app_context():
            started_at = monotonic()
            logger.info(
                "백그라운드 분석 작업을 시작합니다. 저장소 ID=%s, 브랜치=%s",
                request.repository_id,
                request.branch,
            )
            try:
                pipeline = create_analysis_pipeline(
                    session=db.session,
                    repository_url=request.repository_url,
                )
                pipeline.run_pipeline(
                    repository_id=request.repository_id,
                    repository_url=request.repository_url,
                    branch=request.branch,
                )
                logger.info(
                    "백그라운드 분석 작업을 완료했습니다. 저장소 ID=%s, 소요 시간=%.2f초",
                    request.repository_id,
                    monotonic() - started_at,
                )
            except Exception as exc:
                logger.exception(
                    "백그라운드 분석 작업에 실패했습니다. 저장소 ID=%s, "
                    "소요 시간=%.2f초, 오류=%s",
                    request.repository_id,
                    monotonic() - started_at,
                    exc,
                )
