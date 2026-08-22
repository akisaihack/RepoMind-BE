"""LLM-only context compaction and budget tests."""

from app.ai.generation.context_builder import LLMContextBuilder
from app.dtos.response_generation import (
    QueryIntent,
    ResponseGenerationInput,
    RetrievedContext,
    VisualizationType,
)


def _input() -> ResponseGenerationInput:
    version = {
        "id": "repository-scoped-version-id",
        "name": "코드 버전 (L10-20)",
        "type": "SYMBOL",
        "metadata": {
            "detail": "1:class:src/AuthController.java:com.example.AuthController:"
            "method:authenticateUser:(LoginRequest)"
        },
    }
    service = {
        "id": "repository-scoped-method-id",
        "name": "AuthenticationManager.authenticate",
        "type": "SYMBOL",
        "metadata": {"detail": "(Authentication)"},
    }
    call = {"source": version, "relation": "CALLS", "target": service}
    return ResponseGenerationInput(
        question="로그인 호출 흐름을 알려줘",
        intent=QueryIntent.FLOW,
        visualization_required=True,
        visualization_type=VisualizationType.CALL_FLOW,
        context=RetrievedContext(
            code=[
                {
                    "graph_node_id": "long-version-id",
                    "method_node_id": "long-method-id",
                    "commit_hash": "abc123",
                    "path": "src/AuthController.java",
                    "class_name": "AuthController",
                    "method_name": "authenticateUser",
                    "similarity": 0.91,
                    "text": "return authenticationManager.authenticate(authentication);",
                }
            ],
            graph=[
                call,
                call,
                {"source": service, "relation": "HAS_VERSION", "target": version},
            ],
        ),
    )


def test_compacts_llm_context_without_transport_fields() -> None:
    context = LLMContextBuilder().build(_input())

    assert context.code[0].model_dump(exclude_none=True) == {
        "path": "src/AuthController.java",
        "symbol": "AuthController.authenticateUser",
        "similarity": 0.91,
        "code": "return authenticationManager.authenticate(authentication);",
    }
    assert [relation.model_dump() for relation in context.relations] == [
        {
            "source": "AuthController.authenticateUser(LoginRequest)",
            "relation": "CALLS",
            "target": "AuthenticationManager.authenticate",
        }
    ]


def test_context_budget_removes_lower_priority_relations_before_code() -> None:
    input_data = _input()
    input_data.context.code[0]["text"] = "x" * 900
    input_data.context.graph.extend(
        {
            "source": {
                "name": f"Caller{index}.run",
                "id": f"caller:{index}",
                "type": "SYMBOL",
            },
            "relation": "CALLS",
            "target": {
                "name": f"Target{index}.run",
                "id": f"target:{index}",
                "type": "SYMBOL",
            },
        }
        for index in range(20)
    )

    context = LLMContextBuilder().build(input_data, max_context_chars=1_200)

    assert context.code
    assert len(context.model_dump_json(exclude_none=True)) <= 1_200
    assert len(context.relations) < 21


def test_default_context_keeps_all_relevant_relations_without_count_limit() -> None:
    input_data = _input()
    input_data.context.graph = [
        {
            "source": {
                "name": f"Caller{index}.run",
                "id": f"caller:{index}",
                "type": "SYMBOL",
            },
            "relation": "CALLS",
            "target": {
                "name": f"Target{index}.run",
                "id": f"target:{index}",
                "type": "SYMBOL",
            },
        }
        for index in range(40)
    ]

    context = LLMContextBuilder().build(input_data)

    assert len(context.relations) == 40
