"""Data Transfer Objects for Session Management API."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionCreateRequest:
    """
    신규 세션(대화방) 생성 요청 데이터.
    
    <pre>
        분석 완료된 레포지토리 ID를 기반으로 대화방을 엽니다.
    </pre>
    
    @param repo_id 대화의 맥락이 될 레포지토리 고유 ID
    @param title 대화방 이름 (선택 사항)
    """
    repo_id: str
    title: str | None = None


@dataclass
class SessionResponse:
    """
    세션 정보 응답 데이터.
    
    @param session_id 발급된 고유 세션 ID
    @param repo_id 이 세션과 연결된 레포지토리 ID
    @param title 대화방 이름
    @param created_at 세션 생성 시각 (ISO 8601)
    @param updated_at 세션 최종 수정 시각 (ISO 8601)
    """
    session_id: str
    repo_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass
class ChatMessageInfo:
    """
    과거 대화 내역의 단일 메시지 요약 정보.
    
    @param message_id 메시지 고유 식별자
    @param role 작성자 ('user' 또는 'assistant')
    @param content 질문 또는 답변 텍스트
    @param structured_answer assistant 구조화 답변 JSON (선택 사항)
    @param created_at 생성 시각 (ISO 8601)
    """
    message_id: str
    role: str
    content: str
    structured_answer: dict[str, Any] | None
    created_at: str


@dataclass
class MessageHistoryResponse:
    """
    특정 세션의 대화 내역 목록 응답 데이터.
    
    @param session_id 세션 ID
    @param messages 메시지 객체 배열 (시간순 정렬)
    """
    session_id: str
    messages: list[ChatMessageInfo] = field(default_factory=list)
