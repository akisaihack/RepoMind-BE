"""① 질문 유형 분류 노드.

역할: 사용자 질문을 "intent" | "impact" | "location" | "flow" 4가지 중
하나로 분류함 (app/dtos/chat.py의 ChatRequest.question_kind와 동일한 값 집합).

입력: state["question"], (있으면) state["question_kind"]
출력: state["question_kind"]

구현 메모 (docs/langgraph_pipeline.md 4.3 참고):
- 프론트가 이미 question_kind를 넘겨줬으면 이 노드는 스킵하거나 검증만
  해도 됨.
- 없으면 LLM 호출로 분류 — 비용/속도상 가벼운 nano 모델
  (.env의 AZURE_OPENAI_NANO_DEPLOYMENT) 사용을 권장.
- 프롬프트는 app/ai/generation/prompts.py에 템플릿으로 분리해서 관리.
"""

from app.ai.rag.state import QAState


def classify_question(state: QAState) -> QAState:
    """질문 유형을 분류해서 state["question_kind"]를 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.3 참고")
