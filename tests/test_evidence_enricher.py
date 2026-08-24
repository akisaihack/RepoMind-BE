"""호출 그래프 BFS 코드 근거 보강 노드 테스트."""

from types import SimpleNamespace
from unittest.mock import patch

from app.ai.rag.nodes.evidence_enricher import enrich_code_evidence


def _chunk(version_id: str, method_name: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        graph_node_id=version_id,
        method_node_id=f"method:{method_name}",
        text=text,
        path=f"src/{method_name}.java",
        class_name="Service",
        method_name=method_name,
        start_line=10,
        end_line=20,
        api_http_method=None,
        api_path=None,
        commit_hash="abc123",
    )


def test_enriches_unambiguous_calls_in_bfs_order(app) -> None:
    generate = _chunk("version:generate", "generateToken", "String generateToken() { ... }")
    sign = _chunk("version:sign", "signToken", "String signToken() { ... }")
    simple_getter = _chunk(
        "version:getPassword",
        "getPassword",
        "String getPassword() { return password; }",
    )
    repository = patch("app.ai.rag.nodes.evidence_enricher.CodeChunkRepository")
    with app.app_context(), repository as repository_class:
        repository_class.return_value.find_by_graph_node_ids.return_value = [
            generate,
            sign,
            simple_getter,
        ]
        result = enrich_code_evidence(
            {
                "question": "로그인 호출 흐름",
                "github_repository_id": 1,
                "selected_target": {"graph_node_id": "version:authenticate"},
                "graph_results": {
                    "nodes": [],
                    "edges": [
                        {
                            "source": "version:authenticate",
                            "target": "method:generateToken",
                            "type": "CALLS",
                        },
                        {
                            "source": "version:authenticate",
                            "target": "method:getPassword",
                            "type": "CALLS",
                        },
                        {
                            "source": "version:authenticate",
                            "target": "method:wrongGetId",
                            "type": "CALLS",
                            "metadata": {"ambiguous": True},
                        },
                        {
                            "source": "method:generateToken",
                            "target": "version:generate",
                            "type": "HAS_VERSION",
                        },
                        {
                            "source": "version:generate",
                            "target": "method:signToken",
                            "type": "CALLS",
                        },
                        {
                            "source": "method:signToken",
                            "target": "version:sign",
                            "type": "HAS_VERSION",
                        },
                        {
                            "source": "method:getPassword",
                            "target": "version:getPassword",
                            "type": "HAS_VERSION",
                        },
                        {
                            "source": "method:wrongGetId",
                            "target": "version:wrongGetId",
                            "type": "HAS_VERSION",
                        },
                    ],
                },
            }
        )

    assert [item["method_name"] for item in result["enriched_code_results"]] == [
        "generateToken",
        "signToken",
    ]
    repository_class.return_value.find_by_graph_node_ids.assert_called_once_with(
        1, ["version:generate", "version:getPassword", "version:sign"]
    )


def test_bfs_stops_at_five_calls_and_avoids_cycle(app) -> None:
    chunks = [
        _chunk(f"version:{depth}", f"method{depth}", f"void method{depth}() {{ work(); }}")
        for depth in range(1, 7)
    ]
    edges = []
    previous_version = "version:start"
    for depth in range(1, 7):
        method_id = f"method:{depth}"
        version_id = f"version:{depth}"
        edges.extend(
            [
                {"source": previous_version, "target": method_id, "type": "CALLS"},
                {"source": method_id, "target": version_id, "type": "HAS_VERSION"},
            ]
        )
        previous_version = version_id
    edges.append({"source": "version:5", "target": "method:1", "type": "CALLS"})

    with app.app_context(), patch(
        "app.ai.rag.nodes.evidence_enricher.CodeChunkRepository"
    ) as repository_class:
        repository_class.return_value.find_by_graph_node_ids.return_value = chunks[:5]
        result = enrich_code_evidence(
            {
                "question": "호출 흐름",
                "github_repository_id": 1,
                "selected_target": {"graph_node_id": "version:start"},
                "graph_results": {"nodes": [], "edges": edges},
            }
        )

    assert [item["method_name"] for item in result["enriched_code_results"]] == [
        "method1",
        "method2",
        "method3",
        "method4",
        "method5",
    ]
    repository_class.return_value.find_by_graph_node_ids.assert_called_once_with(
        1,
        ["version:1", "version:2", "version:3", "version:4", "version:5"],
    )


def test_skips_method_when_multiple_versions_cannot_be_disambiguated(app) -> None:
    with app.app_context(), patch(
        "app.ai.rag.nodes.evidence_enricher.CodeChunkRepository"
    ) as repository_class:
        result = enrich_code_evidence(
            {
                "question": "호출 흐름",
                "github_repository_id": 1,
                "selected_target": {"graph_node_id": "version:start"},
                "graph_results": {
                    "nodes": [],
                    "edges": [
                        {"source": "version:start", "target": "method:run", "type": "CALLS"},
                        {"source": "method:run", "target": "version:old", "type": "HAS_VERSION"},
                        {"source": "method:run", "target": "version:new", "type": "HAS_VERSION"},
                    ],
                },
            }
        )

    assert result == {"enriched_code_results": []}
    repository_class.return_value.find_by_graph_node_ids.assert_not_called()


def test_skips_enrichment_without_selected_method_version(app) -> None:
    with app.app_context(), patch(
        "app.ai.rag.nodes.evidence_enricher.CodeChunkRepository"
    ) as repository_class:
        result = enrich_code_evidence(
            {"question": "질문", "github_repository_id": 1, "graph_results": {}}
        )

    assert result == {"enriched_code_results": []}
    repository_class.assert_not_called()
