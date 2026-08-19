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
