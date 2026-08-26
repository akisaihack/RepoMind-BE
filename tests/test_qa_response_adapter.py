"""Tests for converting completed RAG output to the public chat contract."""

from dataclasses import asdict

from app.adapters.qa_response_adapter import QAResponseAdapter
from app.dtos.response_generation import (
    GeneratedClaim,
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
        "question_kind": "flow",
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

    assert result.questionKind == "flow"
    assert result.summary == response.answer
    assert result.claims[0].kind == "fact"
    assert result.claims[0].evidenceIds == ["method:1", "method:2"]
    assert result.confidence.level == "high"
    assert result.uncertainties == []
    assert result.graph.nodes == []
    assert result.graph.kind == "flow"
    assert result.suggestedQuestions == ["이 흐름을 수정하면 영향 범위가 어떻게 돼?"]

    serialized = asdict(result)
    assert serialized["questionKind"] == "flow"
    assert serialized["claims"][0]["evidenceIds"] == ["method:1", "method:2"]
    assert serialized["evidence"][0]["excerptStartLine"] == 31
    assert serialized["evidence"][0]["fullExcerpt"].startswith("def cancel")
    assert serialized["evidence"][0]["hasMoreAfter"] is True
    assert serialized["suggestedQuestions"] == ["이 흐름을 수정하면 영향 범위가 어떻게 돼?"]


def test_preserves_pull_request_issue_and_legacy_itsm_evidence_types() -> None:
    response = QueryResponse(answer="변경 이유", intent=QueryIntent.HISTORY)
    state = {
        "question": "왜 변경됐어?",
        "github_repository_id": 1,
        "is_sufficient": True,
        "evidence": [
            {
                "id": "pr:5",
                "type": "pr",
                "title": "PR #5",
                "location": "https://github.com/org/repo/pull/5",
                "description": "merged",
            },
            {
                "id": "issue:4",
                "type": "issue",
                "title": "Issue #4",
                "location": "https://github.com/org/repo/issues/4",
                "description": "resolved",
            },
            {
                "id": "legacy:1",
                "type": "itsm",
                "title": "Legacy",
                "location": "",
                "description": "stored response compatibility",
            },
        ],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(state, response)

    assert [item.type for item in result.evidence] == ["pr", "issue", "itsm"]


def test_flow_graph_keeps_endpoint_nodes_reached_via_exposes_edge() -> None:
    # 2026-08-26 회귀 테스트: _FLOW_EDGE_TYPES가 원래 "handled_by"를 갖고 있었는데,
    # Method->Endpoint 관계로 실제 쓰이는 타입은 "EXPOSES"뿐이라서(코드 어디에도
    # "HANDLED_BY"를 만드는 곳이 없음) EXPOSES 엣지가 전부 조용히 걸러지고
    # 엔드포인트 노드가 그래프에서 통째로 사라지는 문제가 있었음. "exposes"로
    # 고친 뒤에는 엔드포인트 노드와 엣지가 그대로 살아남아야 함.
    response = QueryResponse(
        answer="취소 요청은 /api/cancel 엔드포인트에서 처리됩니다.",
        intent=QueryIntent.FLOW,
        visualization=GraphResponse(
            type=VisualizationType.CALL_FLOW,
            nodes=[
                GraphNode(id="method:1", type="METHOD", label="CancelController.cancel"),
                GraphNode(id="endpoint:1", type="API", label="POST /api/cancel"),
            ],
            edges=[
                {
                    "id": "edge:1",
                    "source": "method:1",
                    "target": "endpoint:1",
                    "type": "EXPOSES",
                }
            ],
        ),
    )
    state = {
        "question": "취소 요청은 어느 엔드포인트에서 처리돼?",
        "github_repository_id": 1,
        "is_sufficient": True,
        "evidence": [],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(state, response)

    assert {node.id for node in result.graph.nodes} == {"method:1", "endpoint:1"}
    assert result.graph.edges[0].type == "exposes"
    assert result.graph.kind == "flow"


def test_uses_llm_generated_claims_without_copying_summary() -> None:
    response = QueryResponse(
        answer="JWT 요청 인증 흐름입니다.",
        intent=QueryIntent.FLOW,
        claims=[
            GeneratedClaim(
                id="claim-1",
                kind="fact",
                title="JWT 추출",
                content="Authorization 헤더에서 JWT를 추출합니다.",
                evidenceIds=["evidence:jwt"],
                citations=[
                    {
                        "content": "Authorization 헤더에서 JWT를 추출합니다.",
                        "evidenceIds": ["evidence:jwt", "unknown"],
                    }
                ],
            )
        ],
        uncertainties=["필터 등록 순서는 제공된 근거로 확인할 수 없습니다."],
    )
    state = {
        "question": "JWT 인증 흐름",
        "github_repository_id": 1,
        "is_sufficient": True,
        "evidence": [
            {
                "id": "evidence:jwt",
                "type": "code",
                "title": "JwtFilter.getJwtFromRequest",
                "location": "JwtFilter.java · Line 10–15",
                "description": "JWT 추출 코드",
            }
        ],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(state, response)

    assert result.summary == "JWT 요청 인증 흐름입니다."
    assert result.claims[0].content != result.summary
    assert result.claims[0].evidenceIds == ["evidence:jwt"]
    assert result.claims[0].citations[0].evidenceIds == ["evidence:jwt"]
    assert result.uncertainties == ["필터 등록 순서는 제공된 근거로 확인할 수 없습니다."]


def test_drops_claim_evidence_ids_not_in_the_public_evidence_list() -> None:
    response = QueryResponse(
        answer="답변",
        intent=QueryIntent.EXPLANATION,
        claims=[
            GeneratedClaim(
                id="claim-1",
                kind="fact",
                title="검증된 주장",
                content="검증된 코드만 설명합니다.",
                evidenceIds=["evidence:known", "evidence:unknown"],
            )
        ],
    )
    state = {
        "question": "어디야?",
        "github_repository_id": 1,
        "evidence": [
            {
                "id": "evidence:known",
                "type": "code",
                "title": "Known.method()",
                "location": "Known.java · Line 1",
                "description": "확인된 근거",
            }
        ],
        "graph_results": {"nodes": [], "edges": []},
    }

    result = QAResponseAdapter().adapt(state, response)

    assert result.claims[0].evidenceIds == ["evidence:known"]


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
    assert result.graph.kind == "relationship"
    assert result.graph.edges[0].label == "introduced_in"
    assert result.confidence.level == "medium"


def test_flow_never_falls_back_to_unprojected_retrieval_graph() -> None:
    result = QAResponseAdapter().adapt(
        {
            "question": "로그인 흐름",
            "github_repository_id": 1,
            "evidence": [],
            "graph_results": {
                "nodes": [{"id": "commit:1", "type": "commit", "label": "sha"}],
                "edges": [
                    {
                        "id": "history",
                        "source": "commit:1",
                        "target": "version:1",
                        "type": "INTRODUCED_IN",
                    }
                ],
            },
        },
        {"answer": "근거 부족", "intent": "FLOW"},
    )

    assert result.graph.kind == "flow"
    assert result.graph.nodes == []
    assert result.graph.edges == []


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
