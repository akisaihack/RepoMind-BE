"""QA pipeline final response wiring tests."""

from contextlib import ExitStack
from unittest.mock import patch

from app.ai.rag.nodes import (
    entity_resolver,
    evidence_enricher,
    evidence_fusion,
    evidence_validator,
    graph_retriever,
    question_analyzer,
    response_composer,
    target_selector,
    vector_retriever,
)
from app.ai.rag.pipeline import run_qa_pipeline, run_qa_pipeline_state
from app.dtos.question import QuestionKind


def test_pipeline_passes_question_kind_and_returns_composed_answer() -> None:
    observed_question_kinds = []
    call_order = []

    def classify(state):
        call_order.append("question")
        observed_question_kinds.append(state.get("question_kind"))
        return {"question_kind": state["question_kind"]}

    def resolve(_state):
        call_order.append("entity")
        return {"entity_candidates": []}

    def vector(_state):
        call_order.append("vector")
        return {"vector_results": [{"graph_node_id": "version:1"}]}

    def graph(state):
        call_order.append("graph")
        assert state["vector_results"] == [{"graph_node_id": "version:1"}]
        observed_question_kinds.append(state.get("question_kind"))
        return {"graph_results": {"nodes": [], "edges": []}}

    def select(state):
        call_order.append("target")
        return {"selected_target": state["vector_results"][0]}

    def fuse(_state):
        call_order.append("fusion")
        return {"evidence": [{"id": "evidence:1"}]}

    def enrich(_state):
        call_order.append("enrichment")
        return {"enriched_code_results": []}

    def validate(state):
        call_order.append("validation")
        return {"is_sufficient": True, "retry_count": state.get("retry_count", 0) + 1}

    def compose(_state):
        call_order.append("response")
        return {
            "answer": {
                "answer": "호출 흐름 답변",
                "intent": "FLOW",
                "visualization": None,
            }
        }

    patches = (
        (question_analyzer, "classify_question", classify),
        (entity_resolver, "resolve_entities", resolve),
        (vector_retriever, "search_vector_evidence", vector),
        (target_selector, "select_target", select),
        (graph_retriever, "search_graph_evidence", graph),
        (evidence_enricher, "enrich_code_evidence", enrich),
        (evidence_fusion, "fuse_evidence", fuse),
        (evidence_validator, "validate_evidence_sufficiency", validate),
        (response_composer, "compose_answer", compose),
    )

    with ExitStack() as stack:
        for module, attribute, replacement in patches:
            stack.enter_context(patch.object(module, attribute, replacement))
        result = run_qa_pipeline(
            question="호출 흐름을 알려줘",
            github_repository_id=1,
            question_kind=QuestionKind.FLOW,
        )

    assert result == {
        "answer": "호출 흐름 답변",
        "intent": "FLOW",
        "visualization": None,
    }
    assert observed_question_kinds == [QuestionKind.FLOW, QuestionKind.FLOW]
    assert call_order == [
        "question",
        "entity",
        "vector",
        "target",
        "graph",
        "enrichment",
        "fusion",
        "validation",
        "response",
    ]


def test_pipeline_state_keeps_evidence_and_graph_for_chat_response_adaptation() -> None:
    state = {
        "question": "코드는 어디에 있어?",
        "github_repository_id": 1,
        "question_kind": QuestionKind.LOCATION,
        "vector_results": [],
        "graph_results": {"nodes": [], "edges": []},
        "evidence": [],
        "is_sufficient": False,
        "retry_count": 2,
        "answer": {"answer": "근거를 찾지 못했습니다.", "intent": "EXPLANATION"},
    }

    with patch("app.ai.rag.pipeline.build_graph") as build_graph:
        build_graph.return_value.invoke.return_value = state
        result = run_qa_pipeline_state(
            question="코드는 어디에 있어?",
            github_repository_id=1,
        )

    assert result is state
    build_graph.return_value.invoke.assert_called_once()


def test_pipeline_repeats_vector_graph_and_fusion_in_order_on_retry() -> None:
    call_order = []
    vector_attempt = 0

    def classify(state):
        call_order.append("question")
        return {"question_kind": state["question_kind"]}

    def resolve(_state):
        call_order.append("entity")
        return {"entity_candidates": []}

    def vector(_state):
        nonlocal vector_attempt
        vector_attempt += 1
        call_order.append(f"vector:{vector_attempt}")
        return {"vector_results": [{"graph_node_id": f"version:{vector_attempt}"}]}

    def graph(state):
        call_order.append(f"graph:{vector_attempt}")
        assert state["vector_results"] == [{"graph_node_id": f"version:{vector_attempt}"}]
        return {"graph_results": {"nodes": [], "edges": []}}

    def select(state):
        call_order.append(f"target:{vector_attempt}")
        return {"selected_target": state["vector_results"][0]}

    def fuse(_state):
        call_order.append(f"fusion:{vector_attempt}")
        return {"evidence": []}

    def enrich(_state):
        call_order.append(f"enrichment:{vector_attempt}")
        return {"enriched_code_results": []}

    def validate(state):
        retry_count = state.get("retry_count", 0) + 1
        call_order.append(f"validation:{retry_count}")
        return {"is_sufficient": retry_count >= 2, "retry_count": retry_count}

    def compose(_state):
        call_order.append("response")
        return {
            "answer": {
                "answer": "재검색 후 답변",
                "intent": "FLOW",
                "visualization": None,
            }
        }

    patches = (
        (question_analyzer, "classify_question", classify),
        (entity_resolver, "resolve_entities", resolve),
        (vector_retriever, "search_vector_evidence", vector),
        (target_selector, "select_target", select),
        (graph_retriever, "search_graph_evidence", graph),
        (evidence_enricher, "enrich_code_evidence", enrich),
        (evidence_fusion, "fuse_evidence", fuse),
        (evidence_validator, "validate_evidence_sufficiency", validate),
        (response_composer, "compose_answer", compose),
    )

    with ExitStack() as stack:
        for module, attribute, replacement in patches:
            stack.enter_context(patch.object(module, attribute, replacement))
        result = run_qa_pipeline(
            question="호출 흐름을 알려줘",
            github_repository_id=1,
            question_kind=QuestionKind.FLOW,
        )

    assert result["answer"] == "재검색 후 답변"
    assert call_order == [
        "question",
        "entity",
        "vector:1",
        "target:1",
        "graph:1",
        "enrichment:1",
        "fusion:1",
        "validation:1",
        "vector:2",
        "target:2",
        "graph:2",
        "enrichment:2",
        "fusion:2",
        "validation:2",
        "response",
    ]
