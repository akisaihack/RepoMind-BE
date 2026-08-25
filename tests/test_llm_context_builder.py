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


def test_history_context_preserves_joined_version_commit_and_diff() -> None:
    input_data = _input()
    input_data.intent = QueryIntent.HISTORY
    input_data.context.history = [
        {
            "method": "AuthController.authenticateUser",
            "change_type": "modified",
            "version": {
                "node_id": "version:2",
                "method_key": "method:authenticate",
                "symbol": "AuthController.authenticateUser(LoginRequest)",
                "source_code": "validate();\nlogin();",
                "start_line": 20,
                "end_line": 25,
                "content_hash": "hash-2",
                "evidence_id": "evidence:code:2",
            },
            "commit": {
                "node_id": "commit:2",
                "sha": "def456",
                "message": "fix: 로그인 검증 추가",
                "author": "Developer",
                "committed_at": "2026-08-10T10:00:00Z",
                "evidence_id": "evidence:commit:2",
            },
            "diff": {
                "previous_commit_sha": "abc123",
                "previous_content_hash": "hash-1",
                "added_lines": ["validate();"],
                "removed_lines": [],
            },
        }
    ]

    context = LLMContextBuilder().build(input_data)

    assert context.history[0]["version"]["source_code"] == "validate();\nlogin();"
    assert context.history[0]["commit"]["sha"] == "def456"
    assert context.history[0]["diff"]["added_lines"] == ["validate();"]


def test_history_budget_reduces_verbose_data_before_latest_change() -> None:
    input_data = _input()
    input_data.intent = QueryIntent.HISTORY
    input_data.context.graph = []
    input_data.context.code = []
    input_data.context.history = [
        {
            "method": "Service.run",
            "change_type": "first_observed" if index == 0 else "modified",
            "version": {
                "node_id": f"version:{index}",
                "method_key": "method:run",
                "symbol": "Service.run()",
                "source_code": "x" * 1_000,
                "start_line": 1,
                "end_line": 10,
                "content_hash": f"hash-{index}",
            },
            "commit": {
                "node_id": f"commit:{index}",
                "sha": f"sha-{index}",
                "committed_at": f"2026-08-0{index + 1}T10:00:00Z",
            },
            "diff": {
                "added_lines": ["added" * 100],
                "removed_lines": ["removed" * 100],
            },
        }
        for index in range(3)
    ]

    context = LLMContextBuilder().build(input_data, max_context_chars=1_200)

    assert context.history
    assert context.history[-1]["commit"]["sha"] == "sha-2"
    assert len(context.model_dump_json(exclude_none=True)) <= 1_200
