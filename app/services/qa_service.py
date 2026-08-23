"""Session-scoped orchestration service for repository Q&A."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.adapters.qa_response_adapter import QAResponseAdapter
from app.ai.rag.pipeline import run_qa_pipeline_state
from app.ai.rag.state import QAState
from app.dtos.chat import ChatRequest, ChatResponseData
from app.models.repository import RepositoryAnalysisStatus
from app.repositories.chat_session import ChatSessionStore


class QASessionNotFoundError(Exception):
    """Raised when Q&A is requested for a chat session that does not exist."""


class QARepositoryNotReadyError(Exception):
    """Raised when the session's repository analysis has not completed."""


class QAGitHubRepositoryIdMissingError(Exception):
    """Raised when an analysis-ready repository has no GitHub repository identifier."""


@dataclass(frozen=True)
class QAExecutionContext:
    """The repository identity required to run a session-scoped Q&A request."""

    session_id: UUID
    repository_id: UUID
    github_repository_id: int


class QAService:
    def __init__(
        self,
        chat_session_store: ChatSessionStore,
        *,
        pipeline_runner: Callable[..., QAState] = run_qa_pipeline_state,
        response_adapter: QAResponseAdapter | None = None,
    ) -> None:
        self._chat_session_store = chat_session_store
        self._pipeline_runner = pipeline_runner
        self._response_adapter = response_adapter or QAResponseAdapter()

    def get_execution_context(self, session_id: UUID) -> QAExecutionContext:
        """Resolve and validate the repository identity for a chat session.

        This is deliberately separate from ``ask`` so the API can map lookup
        failures consistently before the RAG pipeline is connected.
        """
        chat_session = self._chat_session_store.get_with_repository(session_id)

        if chat_session is None:
            raise QASessionNotFoundError("Chat session not found.")

        repository = chat_session.repository
        if repository.analysis_status != RepositoryAnalysisStatus.READY.value:
            raise QARepositoryNotReadyError(
                "Repository analysis must be ready before asking questions."
            )
        if repository.github_repository_id is None:
            raise QAGitHubRepositoryIdMissingError(
                "Repository analysis did not produce a GitHub repository ID."
            )

        return QAExecutionContext(
            session_id=chat_session.id,
            repository_id=repository.id,
            github_repository_id=repository.github_repository_id,
        )

    def ask(self, session_id: UUID, request: ChatRequest) -> ChatResponseData:
        """Classify, retrieve, and adapt one question for an existing chat session."""
        context = self.get_execution_context(session_id)
        final_state = self._pipeline_runner(
            question=request.question,
            github_repository_id=context.github_repository_id,
            conversation_id=str(context.session_id),
            question_kind=request.question_kind,
        )
        return self._response_adapter.adapt(final_state, final_state["answer"])


__all__ = [
    "QAExecutionContext",
    "QAGitHubRepositoryIdMissingError",
    "QARepositoryNotReadyError",
    "QASessionNotFoundError",
    "QAService",
    "run_qa_pipeline_state",
]
