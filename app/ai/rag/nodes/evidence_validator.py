"""⑤ 근거 충분성 검증 (Evidence Validator) 노드.

역할: 통합된 근거로 답변 가능한지 판단. 이 노드의 출력이 pipeline.py의
조건부 엣지 분기 기준이 됨 (근거 부족 & 재시도 가능 -> 다시 검색 단계로,
충분 또는 재시도 소진 -> 답변 생성 단계로).

입력: state["evidence"], state["question"]
출력: state["is_sufficient"], state["retry_count"](증가)

구현 (docs/langgraph_pipeline.md 4.8 / docs/qa_retrieval_part_plan.md Step 6 참고):
- 근거가 존재하고, 정확 심볼 후보가 확인된 경우 선택 대상도 그 후보 중
  하나일 때만 충분하다고 판단한다.
- retry_count는 app.ai.rag.state.MAX_RETRIES와 비교해서 무한 루프를
  막는 데 씀 — 이 노드에서 반드시 증가시킴(빠뜨리면 pipeline.py의 조건부
  분기가 무한 루프에 빠질 위험).
"""

from app.ai.rag.state import QAState


def validate_evidence_sufficiency(state: QAState) -> dict:
    """근거 충분성을 판단해서 state["is_sufficient"]/state["retry_count"]를 채워 반환."""
    evidence = state.get("evidence", [])
    retry_count = state.get("retry_count", 0) + 1
    selected_target = state.get("selected_target") or {}
    exact_target_ids = {
        result["method_node_id"] for result in state.get("symbol_results", [])
    }
    selected_target_id = selected_target.get("method_node_id")

    target_matches = not exact_target_ids or selected_target_id in exact_target_ids
    is_sufficient = len(evidence) > 0 and target_matches
    reason = None
    if not evidence:
        reason = "no_evidence"
    elif not target_matches:
        reason = "explicit_symbol_mismatch"

    return {
        "is_sufficient": is_sufficient,
        "retry_count": retry_count,
        "evidence_validation_reason": reason,
    }
