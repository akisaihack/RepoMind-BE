"""Tests for converting completed RAG output to the public chat contract."""

from dataclasses import asdict

from app.adapters.qa_response_adapter import QAResponseAdapter
from app.dtos.response_generation import (
    GraphNode,
    GraphResponse,
    QueryIntent,
    QueryResponse,
    VisualizationType,
)


def test_adapts_grounded_rag_response_with_visualization() -> None:
    response = QueryResponse(
        answer="취소 요청은 컨트롤러에서 서비스로 전달됩니다.",
        intent=QueryIntent.FLOW,
        visualization=GraphResponse(
            type=VisualizationType.CALL_FLOW,
            nodes=[GraphNode(id="method:1", type="SYMBOL", label="CancelController.cancel")],
            edges=[],
        ),
    )
    state = {
        "question": "취소 요청 흐름을 알려줘",
        "github_repository_id": 1,
        "is_sufficient": True,
        "evidence": [
            {
                "id": "method:1",
                "type": "code",
                "title": "CancelController.cancel",
                "location": "CancelController.java:20",
                "description": "취소 요청을 서비스에 전달합니다.",
                "excerpt": "cancelService.cancel();",
                "fullExcerpt": "def cancel():\n    cancelService.cancel();",
                "startLine": 20,
                "endLine": 52,
                "excerptStartLine": 31,
                "excerptEndLine": 45,
                "hasMoreBefore": True,
                "hasMoreAfter": True,
            },
            {
                "id": "method:2",
                "type": "code",
                "title": "CancelService.cancel",
                "location": "CancelService.java:42",
                "description": "취소를 처리합니다.",
                "excerpt": None,
            },
        ],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(state, response)

    assert result.summary == response.answer
    assert result.claims[0].kind == "fact"
    assert result.claims[0].evidenceIds == ["method:1", "method:2"]
    assert result.confidence.level == "high"
    assert result.uncertainties == []
    assert result.graph.nodes[0].type == "symbol"
    assert result.suggestedQuestions == ["이 흐름을 수정하면 영향 범위가 어떻게 돼?"]

    serialized = asdict(result)
    assert serialized["claims"][0]["evidenceIds"] == ["method:1", "method:2"]
    assert serialized["evidence"][0]["excerptStartLine"] == 31
    assert serialized["evidence"][0]["fullExcerpt"].startswith("def cancel")
    assert serialized["evidence"][0]["hasMoreAfter"] is True
    assert serialized["suggestedQuestions"] == ["이 흐름을 수정하면 영향 범위가 어떻게 돼?"]


def test_falls_back_to_retrieval_graph_when_no_visualization_is_available() -> None:
    state = {
        "question": "로그인 처리는 어디에 있어?",
        "github_repository_id": 1,
        "is_sufficient": True,
        "evidence": [
            {
                "id": "method:login",
                "type": "code",
                "title": "AuthService.login",
                "location": "AuthService.java:10",
                "description": "로그인을 처리합니다.",
            }
        ],
        "graph_results": {
            "nodes": [
                {
                    "id": "method:login",
                    "type": "symbol",
                    "label": "AuthService.login",
                    "detail": "String login()",
                },
                {"id": "commit:1", "type": "commit", "label": "a1b2c3d4"},
            ],
            "edges": [
                {
                    "id": "edge:1",
                    "source": "method:login",
                    "target": "commit:1",
                    "type": "INTRODUCED_IN",
                }
            ],
        },
    }

    result = QAResponseAdapter().adapt(
        state,
        {"answer": "AuthService.login에서 처리합니다.", "intent": "EXPLANATION"},
    )

    assert [node.type for node in result.graph.nodes] == ["symbol", "commit"]
    assert result.graph.edges[0].type == "introduced_in"
    assert result.graph.edges[0].label == "introduced_in"
    assert result.confidence.level == "medium"


def test_marks_answer_as_uncertain_when_evidence_is_missing_or_insufficient() -> None:
    state = {
        "question": "이 설계는 왜 이렇게 됐어?",
        "github_repository_id": 1,
        "is_sufficient": False,
        "evidence": [],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(
        state,
        {"answer": "명확한 근거를 찾지 못했습니다.", "intent": "HISTORY"},
    )

    assert result.claims[0].kind == "inference"
    assert result.claims[0].evidenceIds == []
    assert result.confidence.level == "low"
    assert result.uncertainties == ["검색된 근거가 부족해 답변 내용을 확정하기 어렵습니다."]


def test_uses_stated_intent_claim_for_grounded_history_answer() -> None:
    state = {
        "question": "왜 논리 삭제야?",
        "github_repository_id": 1,
        "is_sufficient": True,
        "evidence": [
            {
                "id": "commit:1",
                "type": "commit",
                "title": "논리 삭제 도입",
                "location": "a1b2c3d4",
                "description": "삭제 이력을 보존합니다.",
            }
        ],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(
        state,
        {"answer": "삭제 이력 보존을 위해 도입됐습니다.", "intent": "HISTORY"},
    )

    assert result.claims[0].kind == "stated_intent"
    assert result.claims[0].title == "구현 배경"
