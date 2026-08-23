"""Mock data for Session API."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from app.dtos.sessions import ChatMessageInfo, MessageHistoryResponse, SessionResponse


def get_mock_session_response(repo_id: str, title: str = None) -> SessionResponse:
    """Returns mock data for a newly created chat session."""
    mock_session_id = f"sess_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(UTC).isoformat()
    return SessionResponse(
        session_id=mock_session_id,
        repo_id=repo_id,
        title=title or "새로운 대화",
        created_at=created_at,
        updated_at=created_at,
    )


def get_mock_message_history(session_id: str) -> MessageHistoryResponse:
    """Returns mock chat history for a session."""
    mock_time = datetime.now(UTC).isoformat()
    return MessageHistoryResponse(
        session_id=session_id,
        messages=[
            ChatMessageInfo(
                message_id="msg_001",
                role="user",
                content="회원 탈퇴 처리 로직은 어디에 있어?",
                created_at=mock_time
            ),
            ChatMessageInfo(
                message_id="msg_002",
                role="assistant",
                content="회원 탈퇴는 MemberController와 MemberService에서 처리됩니다.",
                created_at=mock_time
            )
        ]
    )


def get_mock_session_list(repo_id: str = None) -> dict:
    """Returns a mock list of chat sessions."""
    return {
        "sessions": [
            asdict(SessionResponse(
                session_id="sess_mock_abc123",
                repo_id=repo_id or "repo_example1",
                title="데이터베이스 설정 질문",
                created_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            ))
        ]
    }
