"""Response Composer integration tests."""

from unittest.mock import Mock

from app.ai.rag.nodes.response_composer import compose_answer
from app.dtos.question import QuestionKind
from app.dtos.response_generation import QueryIntent, QueryResponse


def test_response_composer_adapts_qa_state_and_stores_json_response() -> None:
    response_service = Mock()
    response_service.generate.return_value = QueryResponse(
        answer="취소 요청은 컨트롤러에서 서비스로 전달됩니다.",
        intent=QueryIntent.FLOW,
        visualization=None,
    )
    state = {
        "question": "취소 요청의 호출 흐름을 알려줘",
        "github_repository_id": 1,
        "question_kind": QuestionKind.FLOW,
        "vector_results": [],
        "graph_results": {"nodes": [], "edges": []},
        "evidence": [],
    }

    result = compose_answer(state, response_service=response_service)

    assert result == {
        "answer": {
            "answer": "취소 요청은 컨트롤러에서 서비스로 전달됩니다.",
            "intent": "FLOW",
            "visualization": None,
            "claims": [],
            "uncertainties": [],
        }
    }
    input_data = response_service.generate.call_args.args[0]
    assert input_data.question == state["question"]
    assert input_data.intent is QueryIntent.FLOW
    assert input_data.visualization_required is True
