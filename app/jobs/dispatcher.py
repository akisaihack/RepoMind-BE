import logging
from abc import ABC, abstractmethod

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
            f"[NoOpDispatcher] Dispatched analysis job for repo '{request.repository_url}' "
            f"(branch: {request.branch}, id: {request.repository_id})"
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
        logger.info(f"Dispatched background thread for {request.repository_url}")

    def _run_job(self, request: AnalysisRequest) -> None:
        """Run the actual pipeline inside an application context."""
        from app.extensions import db
        from app.factories.pipeline import create_analysis_pipeline

        with self._app.app_context():
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
            except Exception as exc:
                logger.exception(f"Background thread failed for {request.repository_url}: {exc}")
