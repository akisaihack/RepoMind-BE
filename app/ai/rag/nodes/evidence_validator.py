"""⑤ 근거 충분성 검증 (Evidence Validator) 노드.

역할: 통합된 근거로 답변 가능한지 판단. 이 노드의 출력이 pipeline.py의
조건부 엣지 분기 기준이 됨 (근거 부족 & 재시도 가능 -> 다시 검색 단계로,
충분 또는 재시도 소진 -> 답변 생성 단계로).

입력: state["evidence"], state["question"]
출력: state["is_sufficient"], state["retry_count"](증가)

구현 메모 (docs/langgraph_pipeline.md 4.8 참고):
- 처음엔 휴리스틱으로 시작 가능 (예: evidence 개수 0이면 무조건 부족).
  나중에 LLM 판단으로 고도화 가능.
- retry_count는 app.ai.rag.state.MAX_RETRIES와 비교해서 무한 루프를
  막는 데 씀 — 이 노드에서 반드시 증가시켜야 함.
"""

from app.ai.rag.state import QAState


def validate_evidence_sufficiency(state: QAState) -> QAState:
    """근거 충분성을 판단해서 state["is_sufficient"]/state["retry_count"]를 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.8 참고")
