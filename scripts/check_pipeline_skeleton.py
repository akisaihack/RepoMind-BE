"""app/ai/rag/pipeline.py의 build_graph()가 만드는 LangGraph 구조가
설계한 순차 검색/조건부 루프대로 동작하는지 확인하는 수동 검증
스크립트. 앱 요청 경로의 일부가 아니라 개발 중 눈으로 확인하기 위한 용도
(scripts/check_chunking.py 등과 같은 패턴).

nodes/*.py는 아직 전부 NotImplementedError를 던지는 상태라서, 이 스크립트
안에서만 각 노드 함수를 "state 일부를 채우고 지나가는" 더미로 임시
monkeypatch한다. nodes/*.py 원본 파일은 건드리지 않음 — Phase 3에서 진짜
로직을 채울 예정.

시나리오 두 개를 돌린다:
  1) 근거가 처음부터 충분한 경우 -> 곧장 response_composer로 가는지 확인
  2) 근거가 계속 부족한 경우 -> retry_count가 MAX_RETRIES에 도달하면
     강제로 response_composer로 빠져나오는지 확인 (무한 루프 방지 확인)

실행: python scripts/check_pipeline_skeleton.py
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

from app.ai.rag.nodes import (
    entity_resolver,
    evidence_fusion,
    evidence_validator,
    graph_retriever,
    question_analyzer,
    response_composer,
    vector_retriever,
)
from app.ai.rag.pipeline import build_graph
from app.ai.rag.state import QAState

# github.com/callicoder/spring-security-react-ant-design-polls-app
SAMPLE_GITHUB_REPOSITORY_ID = 123231656
SAMPLE_QUESTION = "로그인 프로세스 흐름을 알려줘"


def _build_dummy_nodes(call_log: list[str], *, force_sufficient: bool) -> dict:
    """호출 순서를 call_log에 기록하면서 state를 최소한으로만 채우는 더미 노드 세트.

    각 함수는 실제 노드와 동일하게 "state 전체"가 아니라 "자기 책임 필드만
    담은 dict"를 반환한다 — LangGraph가 이 dict를 기존 state에 병합(merge)함.
    """

    def dummy_classify_question(state: QAState) -> dict:
        call_log.append("question_analyzer")
        return {"question_kind": "flow"}

    def dummy_resolve_entities(state: QAState) -> dict:
        call_log.append("entity_resolver")
        return {"entity_candidates": []}

    def dummy_search_vector_evidence(state: QAState) -> dict:
        call_log.append("vector_retriever")
        return {
            "vector_results": [
                {
                    "graph_node_id": f"{SAMPLE_GITHUB_REPOSITORY_ID}:method:dummy",
                    "text": "dummy chunk text",
                    "similarity": 0.9,
                    "path": "Dummy.java",
                    "class_name": "Dummy",
                    "method_name": "dummyMethod",
                    "commit_hash": "deadbeef",
                }
            ]
        }

    def dummy_search_graph_evidence(state: QAState) -> dict:
        call_log.append("graph_retriever")
        assert state.get("vector_results"), "graph_retriever requires vector_results"
        return {"graph_results": {"nodes": [], "edges": []}}

    def dummy_fuse_evidence(state: QAState) -> dict:
        call_log.append("evidence_fusion")
        vector_results = state.get("vector_results", [])
        return {
            "evidence": [
                {"type": "code", "title": item["method_name"]} for item in vector_results
            ]
        }

    def dummy_validate_evidence_sufficiency(state: QAState) -> dict:
        call_log.append("evidence_validator")
        retry_count = state.get("retry_count", 0) + 1
        return {"is_sufficient": force_sufficient, "retry_count": retry_count}

    def dummy_compose_answer(state: QAState) -> dict:
        call_log.append("response_composer")
        return {
            "answer": {
                "summary": "dummy answer",
                "is_sufficient": state.get("is_sufficient", False),
                "retry_count": state.get("retry_count", 0),
            }
        }

    return {
        "classify_question": dummy_classify_question,
        "resolve_entities": dummy_resolve_entities,
        "search_vector_evidence": dummy_search_vector_evidence,
        "search_graph_evidence": dummy_search_graph_evidence,
        "fuse_evidence": dummy_fuse_evidence,
        "validate_evidence_sufficiency": dummy_validate_evidence_sufficiency,
        "compose_answer": dummy_compose_answer,
    }


def _run_scenario(name: str, *, force_sufficient: bool) -> None:
    call_log: list[str] = []
    dummies = _build_dummy_nodes(call_log, force_sufficient=force_sufficient)

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(question_analyzer, "classify_question", dummies["classify_question"])
        )
        stack.enter_context(
            patch.object(entity_resolver, "resolve_entities", dummies["resolve_entities"])
        )
        stack.enter_context(
            patch.object(
                vector_retriever, "search_vector_evidence", dummies["search_vector_evidence"]
            )
        )
        stack.enter_context(
            patch.object(
                graph_retriever, "search_graph_evidence", dummies["search_graph_evidence"]
            )
        )
        stack.enter_context(
            patch.object(evidence_fusion, "fuse_evidence", dummies["fuse_evidence"])
        )
        stack.enter_context(
            patch.object(
                evidence_validator,
                "validate_evidence_sufficiency",
                dummies["validate_evidence_sufficiency"],
            )
        )
        stack.enter_context(
            patch.object(response_composer, "compose_answer", dummies["compose_answer"])
        )

        compiled = build_graph()
        initial_state: QAState = {
            "question": SAMPLE_QUESTION,
            "github_repository_id": SAMPLE_GITHUB_REPOSITORY_ID,
            "retry_count": 0,
        }
        final_state = compiled.invoke(initial_state)

    print(f"\n=== 시나리오: {name} ===")
    print("노드 실행 순서:", " -> ".join(call_log))
    print("최종 retry_count:", final_state.get("retry_count"))
    print("최종 is_sufficient:", final_state.get("is_sufficient"))
    print("최종 answer:", final_state.get("answer"))

    if "answer" not in final_state:
        print("[경고] response_composer까지 도달하지 못함")


def main() -> None:
    _run_scenario("근거가 처음부터 충분한 경우", force_sufficient=True)
    _run_scenario("근거가 계속 부족 -> 재시도 소진까지 도는 경우", force_sufficient=False)


if __name__ == "__main__":
    main()
