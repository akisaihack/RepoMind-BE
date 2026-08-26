"""⓪ 후속 질문 재작성 (Question Rewriter) 노드.

역할: 세션에 이전 대화가 있으면("그거 어떻게 고쳐?"류 후속 질문), 그 맥락을
참고해서 독립적인 질문으로 재작성해서 state["question"]을 덮어씀. 이후
노드(question_analyzer의 유형 분류, vector_retriever의 임베딩 검색,
graph_retriever의 탐색 시작점 선택)가 전부 이 재작성된 질문을 그대로 쓰게
되므로, 검색 정확도 자체가 개선됨 — 답변 생성 프롬프트에만 이력을 곁들이는
방식보다 근본적인 해결책 (자세한 논의는 docs/qa_retrieval_part_plan.md의
"0-14" 섹션 참고).

입력: state["question"], state["conversation_id"]
출력: state["question"] (재작성됐을 때만 — 히스토리가 없거나 재작성 결과가
      원본과 같으면 아무것도 반환하지 않음)

구현 메모 (2026-08-26):
- state["conversation_id"]가 없으면(세션 없이 파이프라인을 직접 호출하는
  스크립트/테스트 등) 이 노드는 완전히 스킵 — LLM 호출도, DB 조회도 안 함.
- 최근 대화 MAX_HISTORY_EXCHANGES(3턴 = 사용자/어시스턴트 메시지 6개)만
  프롬프트에 넣음 — 세션이 길어져도 프롬프트가 무한정 커지지 않게.
- 세션의 첫 질문(이전 메시지가 하나도 없음)이면 참고할 이력이 없으므로
  LLM 호출 없이 바로 스킵.
- 원본 사용자 질문 자체(요청 DTO의 question)는 이 노드와 무관하게
  app/api/v1/chat.py가 그대로 DB에 저장하므로, 여기서 state["question"]을
  덮어써도 채팅 이력에 재작성된 문장이 남지 않음.
- LLM 호출 실패 시 QuestionRewriter가 원본 질문을 그대로 반환하므로(방어적
  폴백), 이 노드는 별도 예외 처리를 하지 않음.
"""

from uuid import UUID

from flask import current_app

from app.ai.question_rewriter import create_azure_question_rewriter
from app.ai.rag.state import QAState
from app.extensions import db
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.repositories.chat_message import ChatMessageStore

MAX_HISTORY_EXCHANGES = 3


def rewrite_follow_up_question(state: QAState) -> dict:
    """세션의 이전 대화를 참고해서 state["question"]을 독립형으로 재작성해 반환."""
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        return {}  # 세션 없이 호출된 경우(스크립트/테스트 등) — 스킵

    messages = ChatMessageStore(db.session).list_by_session(UUID(conversation_id))
    if not messages:
        return {}  # 세션의 첫 질문 — 참고할 이전 대화가 없음

    history = _format_history(messages)
    rewriter = create_azure_question_rewriter(current_app.config)
    rewritten = rewriter.rewrite(state["question"], history)
    if rewritten == state["question"]:
        return {}
    return {"question": rewritten}


def _format_history(messages: list[ChatMessage]) -> str:
    recent = messages[-(MAX_HISTORY_EXCHANGES * 2) :]
    lines = [
        f"{'사용자' if message.role == ChatMessageRole.USER.value else '어시스턴트'}: {message.content}"
        for message in recent
    ]
    return "\n".join(lines)
