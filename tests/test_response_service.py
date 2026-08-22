"""Response service orchestration tests."""

from unittest.mock import Mock

import pytest

from app.ai.answer_generator import AnswerGenerationError
from app.dtos.response_generation import QueryIntent
from app.errors import APIError
from app.sample.mock_response_generation import get_mock_response_generation_input
from app.services.response_service import ResponseService
from app.visualization.visualization_builder import VisualizationBuilder


def test_response_service_combines_answer_and_visualization() -> None:
    answer_generator = Mock()
    answer_generator.generate.return_value = "취소 호출 흐름입니다."
    input_data = get_mock_response_generation_input()
    service = ResponseService(answer_generator, VisualizationBuilder())

    response = service.generate(input_data)

    assert response.answer == "취소 호출 흐름입니다."
    assert response.intent is QueryIntent.FLOW
    assert response.visualization is not None
    answer_generator.generate.assert_called_once_with(input_data)


def test_response_service_hides_answer_provider_exception() -> None:
    answer_generator = Mock()
    answer_generator.generate.side_effect = AnswerGenerationError("secret provider detail")
    service = ResponseService(answer_generator, VisualizationBuilder())

    with pytest.raises(APIError) as exc_info:
        service.generate(get_mock_response_generation_input())

    assert exc_info.value.code == "ANSWER_PROVIDER_ERROR"
    assert exc_info.value.status == 502
    assert "secret" not in str(exc_info.value)
