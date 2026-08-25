"""Minimal adapter boundary for the not-yet-final upstream retrieval output."""

from collections.abc import Mapping
from typing import Any

from app.ai.generation.history_context_builder import HistoryContextBuilder
from app.ai.rag.state import QAState
from app.dtos.question import QuestionKind
from app.dtos.response_generation import (
    QueryIntent,
    ResponseGenerationInput,
    RetrievedContext,
    VisualizationType,
)

_INTENT_BY_QUESTION_KIND = {
    QuestionKind.FLOW: QueryIntent.FLOW,
    QuestionKind.IMPACT: QueryIntent.DEPENDENCY,
    QuestionKind.INTENT: QueryIntent.HISTORY,
    QuestionKind.LOCATION: QueryIntent.EXPLANATION,
}

_VISUALIZATION_BY_QUESTION_KIND = {
    QuestionKind.FLOW: VisualizationType.CALL_FLOW,
    QuestionKind.IMPACT: VisualizationType.DEPENDENCY,
    QuestionKind.INTENT: VisualizationType.CHANGE_HISTORY,
}


class ResponseInputAdapter:
    """Validate an upstream mapping against the internal response input contract."""

    def adapt(self, source: Mapping[str, Any]) -> ResponseGenerationInput:
        return ResponseGenerationInput.model_validate(dict(source))

    def adapt_qa_state(self, state: QAState) -> ResponseGenerationInput:
        """Adapt the current LangGraph retrieval state into the stable boundary DTO."""
        question_kind = QuestionKind(state.get("question_kind", QuestionKind.LOCATION))
        intent = _INTENT_BY_QUESTION_KIND[question_kind]
        visualization_type = _VISUALIZATION_BY_QUESTION_KIND.get(question_kind)
        graph_results = state.get("graph_results", {}) or {}
        graph_nodes = graph_results.get("nodes", [])
        graph_edges = graph_results.get("edges", [])
        evidence = list(state.get("evidence", []))
        history = (
            HistoryContextBuilder().build(graph_nodes, graph_edges, evidence)
            if intent is QueryIntent.HISTORY
            else []
        )

        return ResponseGenerationInput(
            question=state["question"],
            intent=intent,
            target=_target_from(state),
            visualization_required=visualization_type is not None,
            visualization_type=visualization_type,
            context=RetrievedContext(
                code=list(state.get("vector_results", [])),
                graph=_normalize_graph_relations(graph_nodes, graph_edges),
                history=[item.model_dump(exclude_none=True) for item in history],
                evidence=evidence,
            ),
        )


def _target_from(state: QAState) -> str | None:
    selected = state.get("selected_target")
    if selected is None:
        vector_results = state.get("vector_results", [])
        selected = vector_results[0] if vector_results else None
    if selected is None:
        return None
    return selected.get("method_name") or selected.get("class_name") or selected.get("path")


def _normalize_graph_relations(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Join GraphData nodes/edges into DB-backed relation rows for graph builders."""
    nodes_by_id = {node.get("id"): node for node in nodes if node.get("id")}
    relations: list[dict] = []
    for edge in edges:
        source = nodes_by_id.get(edge.get("source"))
        target = nodes_by_id.get(edge.get("target"))
        relation = edge.get("type")
        if source is None or target is None or not relation:
            continue
        relations.append(
            {
                "source": _normalize_node(source),
                "relation": relation,
                "target": _normalize_node(target),
            }
        )
    return relations


def _normalize_node(node: dict) -> dict:
    metadata = dict(node.get("metadata", {}))
    if node.get("detail") is not None:
        metadata.setdefault("detail", node["detail"])
    return {
        "id": node["id"],
        "name": node.get("label", node["id"]),
        "type": node.get("type", "symbol").upper(),
        "metadata": metadata,
    }
