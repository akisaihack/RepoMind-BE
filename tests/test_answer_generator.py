"""LangChain answer generation tests with no external API calls."""

from langchain_core.runnables import RunnableLambda

from app.ai.answer_generator import AnswerGenerator
from app.ai.generation.context_builder import LLMContextBuilder
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


def test_answer_generator_retries_with_smaller_context_after_provider_limit() -> None:
    received = []

    class ProviderLimitError(Exception):
        status_code = 429

    def answer(prompt):
        received.append(prompt.to_string())
        if len(received) == 1:
            raise ProviderLimitError("rate limit exceeded")
        return "축소된 컨텍스트로 생성한 답변"

    input_data = get_mock_response_generation_input()
    input_data.context.code = [
        {
            "path": "app/cancel.py",
            "class_name": "CancelController",
            "method_name": "cancel",
            "text": "x" * 10_000,
        }
    ]
    generator = AnswerGenerator(
        RunnableLambda(answer),
        context_builder=LLMContextBuilder(fallback_max_context_chars=5_000),
    )

    result = generator.generate(input_data)

    assert result == "축소된 컨텍스트로 생성한 답변"
    assert len(received) == 2
    assert len(received[1]) < len(received[0])
