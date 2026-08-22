"""⑤ 근거 충분성 검증 (Evidence Validator) 노드.

역할: 통합된 근거로 답변 가능한지 판단. 이 노드의 출력이 pipeline.py의
조건부 엣지 분기 기준이 됨 (근거 부족 & 재시도 가능 -> 다시 검색 단계로,
충분 또는 재시도 소진 -> 답변 생성 단계로).

입력: state["evidence"], state["question"]
출력: state["is_sufficient"], state["retry_count"](증가)

구현 (docs/langgraph_pipeline.md 4.8 / docs/qa_retrieval_part_plan.md Step 6 참고):
- 휴리스틱: evidence가 1건이라도 있으면 충분(True), 없으면 부족(False).
  나중에 similarity 임계값이나 LLM 판단으로 고도화 가능(지금은 정보가
  부족해도 "일단 있는 근거로 답변 시도"가 낫다고 판단 — 완전히 근거가
  없을 때만 재시도/불확실 처리).
- retry_count는 app.ai.rag.state.MAX_RETRIES와 비교해서 무한 루프를
  막는 데 씀 — 이 노드에서 반드시 증가시킴(빠뜨리면 pipeline.py의 조건부
  분기가 무한 루프에 빠질 위험).
"""

from app.ai.rag.state import QAState


def validate_evidence_sufficiency(state: QAState) -> dict:
    """근거 충분성을 판단해서 state["is_sufficient"]/state["retry_count"]를 채워 반환."""
    evidence = state.get("evidence", [])
    retry_count = state.get("retry_count", 0) + 1
    is_sufficient = len(evidence) > 0

    return {"is_sufficient": is_sufficient, "retry_count": retry_count}
