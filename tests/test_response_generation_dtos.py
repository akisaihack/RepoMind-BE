"""Response generation boundary DTO tests."""

import pytest
from pydantic import ValidationError

from app.adapters.response_input_adapter import ResponseInputAdapter
from app.dtos.response_generation import QueryIntent


def test_adapter_validates_upstream_mapping() -> None:
    result = ResponseInputAdapter().adapt(
        {
            "question": "PaymentService는 무슨 역할을 해?",
            "intent": "EXPLANATION",
            "context": {"code": [{"name": "PaymentService"}]},
        }
    )

    assert result.intent is QueryIntent.EXPLANATION
    assert result.context.graph == []


def test_input_rejects_empty_question() -> None:
    with pytest.raises(ValidationError):
        ResponseInputAdapter().adapt(
            {"question": "  ", "intent": "EXPLANATION", "context": {}}
        )


def test_adapter_converts_latest_qa_state_graph_shape() -> None:
    result = ResponseInputAdapter().adapt_qa_state(
        {
            "question": "결제 취소 호출 흐름을 알려줘",
            "github_repository_id": 1,
            "question_kind": "flow",
            "vector_results": [
                {
                    "graph_node_id": "version:1",
                    "method_node_id": "method:1",
                    "text": "void cancel() {}",
                    "similarity": 0.9,
                    "path": "CancelController.java",
                    "class_name": "CancelController",
                    "method_name": "cancel",
                    "commit_hash": "abc123",
                }
            ],
            "graph_results": {
                "nodes": [
                    {"id": "method:1", "type": "symbol", "label": "Controller.cancel"},
                    {"id": "method:2", "type": "symbol", "label": "Service.cancel"},
                ],
                "edges": [
                    {
                        "id": "edge:1",
                        "source": "method:1",
                        "target": "method:2",
                        "type": "CALLS",
                        "label": "CALLS",
                    }
                ],
            },
            "evidence": [
                {
                    "id": "evidence:code:cancel",
                    "type": "code",
                    "title": "CancelController.cancel",
                    "location": "CancelController.java · Line 10–20",
                    "description": "취소 요청 진입점",
                }
            ],
        }
    )

    assert result.intent is QueryIntent.FLOW
    assert result.visualization_required is True
    assert result.target == "cancel"
    assert result.context.evidence[0]["id"] == "evidence:code:cancel"
    assert result.context.graph == [
        {
            "source": {
                "id": "method:1",
                "name": "Controller.cancel",
                "type": "SYMBOL",
                "metadata": {},
            },
            "relation": "CALLS",
            "target": {
                "id": "method:2",
                "name": "Service.cancel",
                "type": "SYMBOL",
                "metadata": {},
            },
        }
    ]


def test_adapter_uses_selected_target_instead_of_vector_top_one() -> None:
    result = ResponseInputAdapter().adapt_qa_state(
        {
            "question": "로그인 요청 흐름",
            "github_repository_id": 1,
            "question_kind": "flow",
            "vector_results": [
                {
                    "graph_node_id": "version:register",
                    "method_node_id": "method:register",
                    "text": "registerUser();",
                    "similarity": 0.36,
                    "path": "AuthController.java",
                    "class_name": "AuthController",
                    "method_name": "registerUser",
                    "commit_hash": "abc123",
                }
            ],
            "selected_target": {
                "graph_node_id": "version:authenticate",
                "method_node_id": "method:authenticate",
                "path": "AuthController.java",
                "class_name": "AuthController",
                "method_name": "authenticateUser",
                "similarity": 0.35,
                "selection_source": "LLM",
                "selection_reason": "/signin과 일치",
                "confidence": 0.95,
            },
            "graph_results": {"nodes": [], "edges": []},
        }
    )

    assert result.target == "authenticateUser"


def test_adapter_preserves_history_metadata_for_later_context_building() -> None:
    version_metadata = {
        "node_type": "MethodVersion",
        "method_key": "method:authenticate",
        "source_code": "String jwt = generateToken(authentication);",
        "start_line": 23,
        "end_line": 36,
        "content_hash": "content-hash",
    }
    commit_metadata = {
        "node_type": "Commit",
        "sha": "abc123456789",
        "message": "feat: JWT 로그인 추가",
        "author": "Developer",
        "authored_at": "2026-08-01T10:00:00Z",
        "committed_at": "2026-08-01T11:00:00Z",
    }
    result = ResponseInputAdapter().adapt_qa_state(
        {
            "question": "authenticateUser 변경 이력을 알려줘",
            "github_repository_id": 1,
            "question_kind": "intent",
            "graph_results": {
                "nodes": [
                    {
                        "id": "version:authenticate",
                        "type": "symbol",
                        "label": "코드 버전 (L23-36)",
                        "detail": "method:authenticate",
                        "metadata": version_metadata,
                    },
                    {
                        "id": "commit:abc123",
                        "type": "commit",
                        "label": "abc12345",
                        "detail": "abc123456789",
                        "metadata": commit_metadata,
                    },
                ],
                "edges": [
                    {
                        "id": "history:1",
                        "source": "version:authenticate",
                        "target": "commit:abc123",
                        "type": "INTRODUCED_IN",
                    }
                ],
            },
        }
    )

    relation = result.context.graph[0]
    assert relation["source"]["metadata"] == {
        **version_metadata,
        "detail": "method:authenticate",
    }
    assert relation["target"]["metadata"] == {
        **commit_metadata,
        "detail": "abc123456789",
    }
    assert result.context.history[0]["metadata"] == commit_metadata
