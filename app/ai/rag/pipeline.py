"""LangGraph StateGraph 조립 + 컴파일 + 실행 진입점.

배관만 따로 검증하고 싶으면 scripts/check_pipeline_skeleton.py를 실행할 것
(노드를 임시로 monkeypatch해서 그래프가 끝까지 도는지 확인).

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
from app.ai.rag.state import MAX_RETRIES, QAState, QueryResponseState
from app.dtos.question import QuestionKind


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

    흐름:
        START -> question_analyzer -> entity_resolver -> vector_retriever
            -> graph_retriever -> evidence_fusion -> evidence_validator
        evidence_validator --(근거 부족 & retry_count < MAX_RETRIES)--> vector_retriever로 복귀
        evidence_validator --(충분 또는 재시도 소진)--> response_composer -> END

    graph_retriever는 vector_results의 graph_node_id/method_node_id를 탐색
    시작점으로 사용하므로 반드시 vector_retriever 다음에 실행한다. 재검색도
    같은 순차 경로 전체를 다시 실행한다.
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

    # 그래프 탐색 시작점은 벡터 검색 결과에서 가져오므로 순차 실행한다.
    graph.add_edge("entity_resolver", "vector_retriever")
    graph.add_edge("vector_retriever", "graph_retriever")
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
    question_kind: QuestionKind | str | None = None,
) -> QueryResponseState:
    """Run the pipeline and return the final QueryResponse-compatible dictionary.

    ``question_kind`` may be supplied by the caller. If omitted, Question Analyzer
    is responsible for classifying it before retrieval.
    """
    compiled = build_graph()

    initial_state: QAState = {
        "question": question,
        "github_repository_id": github_repository_id,
        "conversation_id": conversation_id,
        "retry_count": 0,
    }
    if question_kind is not None:
        initial_state["question_kind"] = QuestionKind(question_kind)

    final_state = compiled.invoke(initial_state)
    return final_state["answer"]


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
