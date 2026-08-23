"""Session-scoped orchestration service for repository Q&A."""

from dataclasses import dataclass
from uuid import UUID

from app.ai.rag.pipeline import run_qa_pipeline
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
    def __init__(self, chat_session_store: ChatSessionStore) -> None:
        self._chat_session_store = chat_session_store

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

    def ask(self, session_id: str, request: ChatRequest) -> ChatResponseData:
        """질문을 받아 파이프라인을 실행하고 ChatResponseData를 반환.

        app/api/v1/chat.py의
        `# TODO: 실제 RAG 파이프라인 연동 시 아래 목(Mock) 데이터를 삭제하고
        실제 생성 로직으로 교체` 자리에서 이 메서드를 호출하도록 교체하면 됨
        (get_mock_chat_response() 대신 이 메서드 호출).
        """
        raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.11 참고")


__all__ = [
    "QAExecutionContext",
    "QAGitHubRepositoryIdMissingError",
    "QARepositoryNotReadyError",
    "QASessionNotFoundError",
    "QAService",
    "run_qa_pipeline",
]
