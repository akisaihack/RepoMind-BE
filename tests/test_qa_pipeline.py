"""QA pipeline final response wiring tests."""

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
from app.ai.rag.pipeline import run_qa_pipeline
from app.dtos.question import QuestionKind


def test_pipeline_passes_question_kind_and_returns_composed_answer() -> None:
    observed_question_kinds = []

    def classify(state):
        observed_question_kinds.append(state.get("question_kind"))
        return {"question_kind": state["question_kind"]}

    def resolve(_state):
        return {"entity_candidates": []}

    def vector(_state):
        return {"vector_results": []}

    def graph(state):
        observed_question_kinds.append(state.get("question_kind"))
        return {"graph_results": {"nodes": [], "edges": []}}

    def fuse(_state):
        return {"evidence": [{"id": "evidence:1"}]}

    def validate(state):
        return {"is_sufficient": True, "retry_count": state.get("retry_count", 0) + 1}

    def compose(_state):
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
        (graph_retriever, "search_graph_evidence", graph),
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
