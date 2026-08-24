"""Deterministic visualization builder tests."""

from app.dtos.response_generation import (
    QueryIntent,
    ResponseGenerationInput,
    RetrievedContext,
    VisualizationType,
)
from app.sample.mock_response_generation import get_mock_response_generation_input
from app.visualization.visualization_builder import VisualizationBuilder


def test_call_flow_builds_unique_nodes_and_edges() -> None:
    result = VisualizationBuilder().build(get_mock_response_generation_input())

    assert result is not None
    assert result.type is VisualizationType.CALL_FLOW
    assert [node.id for node in result.nodes] == ["method:1", "method:2", "method:3"]
    assert [node.label for node in result.nodes] == [
        "CancelController.cancel()",
        "CancelService.cancel()",
        "PaymentService.cancel()",
    ]
    assert [edge.id for edge in result.edges] == [
        "method:1:CALLS:method:2",
        "method:2:CALLS:method:3",
    ]


def test_visualization_is_none_when_not_required() -> None:
    input_data = ResponseGenerationInput(
        question="PaymentService는 무슨 역할을 해?",
        intent=QueryIntent.EXPLANATION,
        context=RetrievedContext(code=[{"name": "PaymentService"}]),
    )

    assert VisualizationBuilder().build(input_data) is None


def test_visualization_is_none_when_graph_is_empty() -> None:
    input_data = ResponseGenerationInput(
        question="호출 흐름을 알려줘",
        intent=QueryIntent.FLOW,
        visualization_required=True,
        visualization_type=VisualizationType.CALL_FLOW,
        context=RetrievedContext(),
    )

    assert VisualizationBuilder().build(input_data) is None


def test_unsupported_visualization_is_none() -> None:
    input_data = get_mock_response_generation_input().model_copy(
        update={"visualization_type": VisualizationType.DEPENDENCY}
    )

    assert VisualizationBuilder().build(input_data) is None


def test_call_flow_projects_versions_and_drops_internal_or_isolated_nodes() -> None:
    controller = {"id": "method:controller", "name": "UserController.login", "type": "SYMBOL"}
    controller_version = {"id": "version:controller", "name": "코드 버전", "type": "SYMBOL"}
    service = {"id": "method:service", "name": "AuthService.login", "type": "SYMBOL"}
    endpoint = {"id": "api:login", "name": "POST /api/login", "type": "API"}
    commit = {"id": "commit:1", "name": "commit", "type": "COMMIT"}
    input_data = ResponseGenerationInput(
        question="로그인 흐름",
        intent=QueryIntent.FLOW,
        visualization_required=True,
        visualization_type=VisualizationType.CALL_FLOW,
        context=RetrievedContext(
            graph=[
                {"source": controller, "relation": "HAS_VERSION", "target": controller_version},
                {"source": controller_version, "relation": "CALLS", "target": service},
                {"source": controller, "relation": "EXPOSES", "target": endpoint},
                {"source": controller_version, "relation": "INTRODUCED_IN", "target": commit},
            ]
        ),
    )

    result = VisualizationBuilder().build(input_data)

    assert result is not None
    assert [node.id for node in result.nodes] == [
        "method:controller",
        "method:service",
        "api:login",
    ]
    assert [(edge.source, edge.type, edge.target) for edge in result.edges] == [
        ("api:login", "HANDLED_BY", "method:controller"),
        ("method:controller", "CALLS", "method:service"),
    ]


def test_call_flow_is_none_without_a_call_relation() -> None:
    method = {"id": "method:controller", "name": "UserController.login", "type": "SYMBOL"}
    endpoint = {"id": "api:login", "name": "POST /api/login", "type": "API"}
    input_data = ResponseGenerationInput(
        question="로그인 흐름",
        intent=QueryIntent.FLOW,
        visualization_required=True,
        visualization_type=VisualizationType.CALL_FLOW,
        context=RetrievedContext(
            graph=[{"source": method, "relation": "EXPOSES", "target": endpoint}]
        ),
    )

    assert VisualizationBuilder().build(input_data) is None
