"""벡터 검색 후보 중 질문과 가장 일치하는 분석 대상을 선택하는 노드."""

from flask import current_app

from app.ai.rag.state import QAState
from app.ai.target_selector import create_azure_target_selector


def select_target(state: QAState) -> dict:
    selector = create_azure_target_selector(current_app.config)
    selected = selector.select(state["question"], state.get("vector_results", []))
    return {"selected_target": selected.model_dump(mode="json") if selected else None}

