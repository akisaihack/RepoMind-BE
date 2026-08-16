"""⑥ 답변 생성 (Response Composer) 노드 — 파이프라인의 최종 출력을 만듦.

역할: 근거를 바탕으로 "확인된 사실 / 명시된 의도 / 추론된 의도"를 구분한
답변을 LLM으로 생성하고, app.dtos.chat.ChatResponseData와 완전히 동일한
형태로 조립.

입력: state["evidence"], state["question"], state["question_kind"]
출력: state["answer"] (ChatResponseData 호환 dict)

구현 메모 (docs/langgraph_pipeline.md 4.9 참고):
- LLM 호출 — 답변 생성용 모델(.env의 AZURE_OPENAI_DEPLOYMENT, mini급) 사용
  권장. app.services.embedding.EmbeddingService와 비슷한 패턴으로
  ChatCompletionService 같은 걸 새로 만들어야 함(아직 없음).
- 프롬프트는 app/ai/generation/prompts.py에서 관리 — "근거 없으면 의도를
  확정적으로 표현하지 않는다"는 원칙을 프롬프트에 명시적으로 강제해야 함.
- 출력은 app.sample.mock_chat.get_mock_chat_response()의 반환값과 완전히
  같은 구조여야 함 — 그래야 app/api/v1/chat.py의 TODO 자리(mock 호출)를
  실제 호출로 한 줄만 바꿔서 교체 가능.
  claims[].kind는 반드시 "fact" | "stated_intent" | "inference" 중 하나로
  채울 것 (app.dtos.chat.Claim 참고).
"""

from app.ai.rag.state import QAState


def compose_answer(state: QAState) -> QAState:
    """근거를 바탕으로 ChatResponseData 호환 답변을 만들어 state["answer"]에 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.9 참고")
