from types import SimpleNamespace
from unittest.mock import patch

from app.ai.rag.nodes.entity_resolver import resolve_entities


def test_resolves_question_symbol_to_repository_chunk(app) -> None:
    chunk = SimpleNamespace(
        graph_node_id="version:requestExport",
        method_node_id="method:requestExport",
        text="function requestExport(spinKey) {}",
        path="static/embed.js",
        class_name="embed$module",
        method_name="requestExport",
        param_signature="(spinKey)",
        start_line=10,
        end_line=12,
        api_http_method=None,
        api_path=None,
        commit_hash="abc123",
    )

    with app.app_context(), patch(
        "app.ai.rag.nodes.entity_resolver.CodeChunkRepository"
    ) as repository_class:
        repository_class.return_value.find_by_exact_symbol_names.return_value = [chunk]
        result = resolve_entities(
            {
                "question": "requestExport 함수에서 spinKey를 제거한 이유는?",
                "github_repository_id": 100,
            }
        )

    repository_class.return_value.find_by_exact_symbol_names.assert_called_once_with(
        100, ["requestExport", "spinKey"]
    )
    assert result["explicit_symbol_names"] == ["requestExport", "spinKey"]
    assert result["symbol_results"][0]["method_node_id"] == "method:requestExport"


def test_deduplicates_method_versions_for_exact_symbol(app) -> None:
    common = {
        "method_node_id": "method:requestExport",
        "text": "function requestExport() {}",
        "path": "static/embed.js",
        "class_name": "embed$module",
        "method_name": "requestExport",
        "param_signature": "()",
        "start_line": 10,
        "end_line": 12,
        "api_http_method": None,
        "api_path": None,
        "commit_hash": "abc123",
    }
    chunks = [
        SimpleNamespace(graph_node_id="version:new", **common),
        SimpleNamespace(graph_node_id="version:old", **common),
    ]

    with app.app_context(), patch(
        "app.ai.rag.nodes.entity_resolver.CodeChunkRepository"
    ) as repository_class:
        repository_class.return_value.find_by_exact_symbol_names.return_value = chunks
        result = resolve_entities(
            {"question": "requestExport 함수", "github_repository_id": 100}
        )

    assert [item["graph_node_id"] for item in result["symbol_results"]] == ["version:new"]
