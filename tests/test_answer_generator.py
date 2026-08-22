"""LangChain answer generation tests with no external API calls."""

from langchain_core.runnables import RunnableLambda

from app.ai.answer_generator import AnswerGenerator
from app.sample.mock_response_generation import get_mock_response_generation_input


def test_answer_generator_uses_langchain_without_external_api() -> None:
    received = []

    def answer(prompt):
        received.append(prompt)
        return "결제 취소 요청은 컨트롤러에서 서비스 순서로 처리됩니다."

    generator = AnswerGenerator(RunnableLambda(answer))

    result = generator.generate(get_mock_response_generation_input())

    assert result == "결제 취소 요청은 컨트롤러에서 서비스 순서로 처리됩니다."
    prompt_text = received[0].to_string()
    assert "호출 순서 중심" in prompt_text
    assert "CancelController.cancel" in prompt_text
    assert "JSON 시각화 데이터는 생성하지 마세요" in prompt_text
