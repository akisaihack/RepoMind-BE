"""Convert internal RAG output into the public chat response contract."""

from collections.abc import Mapping
from typing import Any, Literal

from app.ai.rag.state import QAState
from app.dtos.chat import (
    ChatResponseData,
    Claim,
    Confidence,
    Evidence,
    GraphData,
    GraphEdge,
    GraphNode,
)
from app.dtos.response_generation import QueryIntent, QueryResponse

_CLAIM_TITLE_BY_INTENT = {
    QueryIntent.FLOW: "주요 실행 흐름",
    QueryIntent.DEPENDENCY: "예상 영향 범위",
    QueryIntent.HISTORY: "구현 배경",
    QueryIntent.EXPLANATION: "관련 코드 위치와 역할",
}

_SUGGESTED_QUESTIONS_BY_INTENT = {
    QueryIntent.FLOW: ["이 흐름을 수정하면 영향 범위가 어떻게 돼?"],
    QueryIntent.DEPENDENCY: ["영향을 가장 적게 받도록 수정하려면 어떻게 해야 해?"],
    QueryIntent.HISTORY: ["이 결정이 도입된 변경 이력을 더 보여줘."],
    QueryIntent.EXPLANATION: ["이 코드가 호출되는 흐름을 알려줘."],
}

_GRAPH_NODE_TYPES = {"api", "symbol", "commit"}
_EVIDENCE_TYPES = {"code", "itsm", "commit"}


class QAResponseAdapter:
    """Build a frontend-compatible ``ChatResponseData`` from a completed QA state."""

    def adapt(
        self,
        state: QAState,
        response: QueryResponse | Mapping[str, Any],
    ) -> ChatResponseData:
        query_response = QueryResponse.model_validate(response)
        evidence = _evidence_from(state.get("evidence", []))
        has_sufficient_evidence = bool(state.get("is_sufficient", bool(evidence)))
        confidence, uncertainties = _confidence_from(
            evidence_count=len(evidence),
            has_sufficient_evidence=has_sufficient_evidence,
        )

        claims = _claims_from(query_response, evidence)
        uncertainties = list(
            dict.fromkeys([*query_response.uncertainties, *uncertainties])
        )

        return ChatResponseData(
            summary=query_response.answer,
            claims=claims,
            evidence=evidence,
            confidence=confidence,
            graph=_graph_from(state, query_response),
            uncertainties=uncertainties,
            suggestedQuestions=_SUGGESTED_QUESTIONS_BY_INTENT[query_response.intent],
        )


def _claims_from(query_response: QueryResponse, evidence: list[Evidence]) -> list[Claim]:
    evidence_ids = {item.id for item in evidence}
    if query_response.claims:
        return [
            Claim(
                id=claim.id,
                kind=claim.kind,
                title=claim.title,
                content=claim.content,
                evidenceIds=[item_id for item_id in claim.evidence_ids if item_id in evidence_ids],
            )
            for claim in query_response.claims
        ]

    claim_kind: Literal["fact", "stated_intent", "inference"]
    if not evidence:
        claim_kind = "inference"
    elif query_response.intent is QueryIntent.HISTORY:
        claim_kind = "stated_intent"
    else:
        claim_kind = "fact"
    return [
        Claim(
            id=f"answer:{query_response.intent.value.lower()}",
            kind=claim_kind,
            title=_CLAIM_TITLE_BY_INTENT[query_response.intent],
            content=query_response.answer,
            evidenceIds=[item.id for item in evidence],
        )
    ]


def _evidence_from(raw_evidence: object) -> list[Evidence]:
    if not isinstance(raw_evidence, list):
        return []

    evidence: list[Evidence] = []
    for raw_item in raw_evidence:
        if not isinstance(raw_item, Mapping):
            continue
        item_id = raw_item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        evidence_type = raw_item.get("type")
        normalized_type = evidence_type if evidence_type in _EVIDENCE_TYPES else "code"
        evidence.append(
            Evidence(
                id=item_id,
                type=normalized_type,
                title=_string_or_empty(raw_item.get("title")),
                location=_string_or_empty(raw_item.get("location")),
                description=_string_or_empty(raw_item.get("description")),
                excerpt=_optional_string(raw_item.get("excerpt")),
                fullExcerpt=_optional_string(raw_item.get("fullExcerpt")),
                startLine=_optional_int(raw_item.get("startLine")),
                endLine=_optional_int(raw_item.get("endLine")),
                excerptStartLine=_optional_int(raw_item.get("excerptStartLine")),
                excerptEndLine=_optional_int(raw_item.get("excerptEndLine")),
                hasMoreBefore=raw_item.get("hasMoreBefore") is True,
                hasMoreAfter=raw_item.get("hasMoreAfter") is True,
            )
        )
    return evidence


def _graph_from(state: QAState, response: QueryResponse) -> GraphData:
    if response.visualization is not None:
        return GraphData(
            nodes=[_graph_node_from(node.model_dump()) for node in response.visualization.nodes],
            edges=[_graph_edge_from(edge.model_dump()) for edge in response.visualization.edges],
            kind=_graph_kind(response.intent),
        )

    graph_results = state.get("graph_results", {}) or {}
    raw_nodes = graph_results.get("nodes", []) if isinstance(graph_results, Mapping) else []
    raw_edges = graph_results.get("edges", []) if isinstance(graph_results, Mapping) else []
    return GraphData(
        nodes=[_graph_node_from(node) for node in raw_nodes if isinstance(node, Mapping)],
        edges=[_graph_edge_from(edge) for edge in raw_edges if isinstance(edge, Mapping)],
        kind=_graph_kind(response.intent),
    )


def _graph_kind(intent: QueryIntent) -> Literal["flow", "impact", "history", "relationship"]:
    return {
        QueryIntent.FLOW: "flow",
        QueryIntent.DEPENDENCY: "impact",
        QueryIntent.HISTORY: "history",
        QueryIntent.EXPLANATION: "relationship",
    }[intent]


def _graph_node_from(raw_node: Mapping[str, Any]) -> GraphNode:
    raw_type = raw_node.get("type")
    node_type = raw_type.lower() if isinstance(raw_type, str) else "symbol"
    if node_type not in _GRAPH_NODE_TYPES:
        node_type = "symbol"
    return GraphNode(
        id=_string_or_empty(raw_node.get("id")),
        type=node_type,
        label=_string_or_empty(raw_node.get("label")),
        detail=_optional_string(raw_node.get("detail")),
    )


def _graph_edge_from(raw_edge: Mapping[str, Any]) -> GraphEdge:
    edge_type = _string_or_empty(raw_edge.get("type")).lower()
    return GraphEdge(
        id=_string_or_empty(raw_edge.get("id")),
        source=_string_or_empty(raw_edge.get("source")),
        target=_string_or_empty(raw_edge.get("target")),
        type=edge_type,
        label=_optional_string(raw_edge.get("label")) or edge_type,
    )


def _confidence_from(
    *, evidence_count: int, has_sufficient_evidence: bool
) -> tuple[Confidence, list[str]]:
    if evidence_count == 0 or not has_sufficient_evidence:
        return (
            Confidence(
                level="low",
                reason="질문과 직접 연결되는 확인 가능한 근거가 충분하지 않습니다.",
            ),
            ["검색된 근거가 부족해 답변 내용을 확정하기 어렵습니다."],
        )
    if evidence_count == 1:
        return (
            Confidence(
                level="medium",
                reason="하나의 관련 근거를 확인했지만 추가 교차 검증이 필요합니다.",
            ),
            [],
        )
    return (
        Confidence(
            level="high",
            reason="여러 코드 또는 이력 근거를 교차 확인했습니다.",
        ),
        [],
    )


def _string_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = ["QAResponseAdapter"]
