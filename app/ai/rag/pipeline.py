"""LangGraph StateGraph 조립 + 컴파일 + 실행 진입점.

Phase 1(배관 검증) 완료: 노드 7개는 아직 nodes/*.py에서 전부
NotImplementedError를 던지는 상태지만, 그래프 구조(순서/병렬 분기/조건부
루프) 자체는 여기서 실제로 조립된다. 노드 내용은 Phase 3에서 하나씩
채운다 — 이 파일은 그때도 그대로 재사용됨.

배관만 따로 검증하고 싶으면 scripts/check_pipeline_skeleton.py를 실행할 것
(7개 노드를 임시로 monkeypatch해서 그래프가 끝까지 도는지 확인).

pip install -e '.[dev,postgres]'로 langgraph 패키지를 설치해야 이 파일의
import가 동작함 (pyproject.toml에 이미 추가해둠).
"""

from langgraph.graph import END, START, StateGraph

from app.ai.rag.nodes import (
    entity_resolver,
    evidence_fusion,
    evidence_validator,
    graph_retriever,
    question_analyzer,
    response_composer,
    vector_retriever,
)
from app.ai.rag.state import MAX_RETRIES, QAState


def _route_after_validation(state: QAState) -> str:
    """evidence_validator 다음 분기 함수 — add_conditional_edges의 기준.

    "compose"를 반환하면 response_composer로, "retry"를 반환하면 다시
    검색 단계로 돌아간다. retry_count >= MAX_RETRIES 체크가 반드시
    여기 있어야 무한 루프를 막을 수 있음.
    """
    if state.get("is_sufficient"):
        return "compose"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        return "compose"
    return "retry"


def build_graph():
    """7개 노드를 조립한 LangGraph를 컴파일해서 반환.

    흐름 (docs/langgraph_pipeline.md 1번 섹션 다이어그램과 동일):
        START -> question_analyzer -> entity_resolver
            -> vector_retriever \\
            -> graph_retriever   >-> evidence_fusion -> evidence_validator
        evidence_validator --(근거 부족 & retry_count < MAX_RETRIES)--> vector_retriever로 복귀
        evidence_validator --(충분 또는 재시도 소진)--> response_composer -> END

    알려진 위험(Phase 1에서 실제로 확인 필요): 재시도 루프가 vector_retriever
    로만 돌아가고 graph_retriever는 다시 안 도는데, evidence_fusion은 두
    노드(vector_retriever + graph_retriever) 결과를 둘 다 기다렸다가
    합류(join)하는 구조라서, 재시도 시 evidence_fusion이 다시 안 돌 수도
    있음. scripts/check_pipeline_skeleton.py의 "재시도 소진까지 도는 경우"
    시나리오에서 response_composer까지 실제로 도달하는지로 확인할 것 —
    만약 안 되면 retry 분기 대상을 vector_retriever/graph_retriever 둘 다로
    바꿔야 함.
    """
    graph = StateGraph(QAState)

    graph.add_node("question_analyzer", question_analyzer.classify_question)
    graph.add_node("entity_resolver", entity_resolver.resolve_entities)
    graph.add_node("vector_retriever", vector_retriever.search_vector_evidence)
    graph.add_node("graph_retriever", graph_retriever.search_graph_evidence)
    graph.add_node("evidence_fusion", evidence_fusion.fuse_evidence)
    graph.add_node("evidence_validator", evidence_validator.validate_evidence_sufficiency)
    graph.add_node("response_composer", response_composer.compose_answer)

    graph.add_edge(START, "question_analyzer")
    graph.add_edge("question_analyzer", "entity_resolver")

    # entity_resolver 뒤에서 벡터 검색 / 그래프 탐색이 병렬로 갈라짐
    graph.add_edge("entity_resolver", "vector_retriever")
    graph.add_edge("entity_resolver", "graph_retriever")

    # 두 검색 결과가 evidence_fusion에서 합류(join)
    graph.add_edge("vector_retriever", "evidence_fusion")
    graph.add_edge("graph_retriever", "evidence_fusion")

    graph.add_edge("evidence_fusion", "evidence_validator")

    graph.add_conditional_edges(
        "evidence_validator",
        _route_after_validation,
        {
            "retry": "vector_retriever",
            "compose": "response_composer",
        },
    )

    graph.add_edge("response_composer", END)

    return graph.compile()


def run_qa_pipeline(
    question: str,
    github_repository_id: int,
    conversation_id: str | None = None,
) -> dict:
    """파이프라인 진입점. 초기 QAState를 만들고 컴파일된 그래프를 실행해서
    최종 answer(ChatResponseData 호환 dict)를 꺼내 반환.

    app/services/qa_service.py가 이 함수를 호출함.
    """
    compiled = build_graph()

    initial_state: QAState = {
        "question": question,
        "github_repository_id": github_repository_id,
        "conversation_id": conversation_id,
        "retry_count": 0,
    }

    final_state = compiled.invoke(initial_state)
    return final_state.get("answer", {})


__all__ = [
    "MAX_RETRIES",
    "QAState",
    "build_graph",
    "entity_resolver",
    "evidence_fusion",
    "evidence_validator",
    "graph_retriever",
    "question_analyzer",
    "response_composer",
    "run_qa_pipeline",
    "vector_retriever",
]
