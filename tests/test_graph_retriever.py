"""선택된 분석 대상이 Neo4j 탐색 시작점으로 사용되는지 검증."""

from unittest.mock import MagicMock, patch

from app.ai.rag.nodes import graph_retriever
from app.dtos.question import QuestionKind


def test_uses_selected_target_instead_of_vector_top_one(app) -> None:
    state = {
        "question": "로그인 호출 흐름",
        "github_repository_id": 1,
        "question_kind": QuestionKind.FLOW,
        "vector_results": [
            {"graph_node_id": "version:register", "method_node_id": "method:register"}
        ],
        "selected_target": {
            "graph_node_id": "version:authenticate",
            "method_node_id": "method:authenticate",
        },
    }
    client = MagicMock()
    context_manager = MagicMock()
    context_manager.__enter__.return_value = client
    context_manager.__exit__.return_value = None

    calls_forward = MagicMock(return_value={"nodes": [], "edges": []})
    with app.app_context(), patch(
        "app.ai.rag.nodes.graph_retriever.Neo4jClient.from_config",
        return_value=context_manager,
    ), patch.dict(
        graph_retriever._STRATEGY_BY_QUESTION_KIND,
        {QuestionKind.FLOW: calls_forward},
    ):
        graph_retriever.search_graph_evidence(state)

    calls_forward.assert_called_once_with(client, "version:authenticate")
