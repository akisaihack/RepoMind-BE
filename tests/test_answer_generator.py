"""LangChain answer generation tests with no external API calls."""

import json

from langchain_core.runnables import RunnableLambda

from app.ai.answer_generator import AnswerGenerator
from app.ai.generation.context_builder import LLMContextBuilder
from app.sample.mock_response_generation import get_mock_response_generation_input


def test_answer_generator_uses_langchain_without_external_api() -> None:
    received = []

    def answer(prompt):
        received.append(prompt)
        return json.dumps(
            {
                "summary": "결제 취소 호출 흐름입니다.",
                "claims": [
                    {
                        "id": "claim-1",
                        "kind": "fact",
                        "title": "호출 흐름",
                        "content": "컨트롤러에서 서비스 순서로 처리됩니다.",
                        "evidenceIds": [],
                    }
                ],
                "uncertainties": [],
            },
            ensure_ascii=False,
        )

    generator = AnswerGenerator(RunnableLambda(answer))

    result = generator.generate(get_mock_response_generation_input())

    assert result.summary == "결제 취소 호출 흐름입니다."
    assert result.claims[0].content == "컨트롤러에서 서비스 순서로 처리됩니다."
    prompt_text = received[0].to_string()
    assert "호출 순서 중심" in prompt_text
    assert "CancelController.cancel" in prompt_text
    assert "JSON 시각화 데이터는 생성하지 마세요" in prompt_text
    assert '"summary"' in prompt_text


def test_answer_generator_retries_with_smaller_context_after_provider_limit() -> None:
    received = []

    class ProviderLimitError(Exception):
        status_code = 429

    def answer(prompt):
        received.append(prompt.to_string())
        if len(received) == 1:
            raise ProviderLimitError("rate limit exceeded")
        return json.dumps(
            {
                "summary": "축소된 컨텍스트로 생성한 답변",
                "claims": [
                    {
                        "id": "claim-1",
                        "kind": "inference",
                        "title": "답변",
                        "content": "축소된 컨텍스트로 생성한 답변",
                        "evidenceIds": [],
                    }
                ],
                "uncertainties": [],
            },
            ensure_ascii=False,
        )

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

    assert result.summary == "축소된 컨텍스트로 생성한 답변"
    assert len(received) == 2
    assert len(received[1]) < len(received[0])


def test_answer_generator_removes_unknown_and_duplicate_evidence_ids() -> None:
    input_data = get_mock_response_generation_input()
    input_data.context.evidence = [
        {
            "id": "evidence:code:valid",
            "type": "code",
            "title": "CancelService.cancel",
            "location": "CancelService.java · Line 10–20",
            "description": "취소 처리 코드",
        }
    ]

    def answer(_prompt):
        return json.dumps(
            {
                "summary": "취소 흐름입니다.",
                "claims": [
                    {
                        "id": "claim-1",
                        "kind": "fact",
                        "title": "취소 처리",
                        "content": "서비스에서 취소합니다.",
                        "evidenceIds": [
                            "evidence:code:valid",
                            "invented-id",
                            "evidence:code:valid",
                        ],
                    }
                ],
                "uncertainties": [],
            }
        )

    result = AnswerGenerator(RunnableLambda(answer)).generate(input_data)

    assert result.claims[0].evidence_ids == ["evidence:code:valid"]


def test_answer_generator_falls_back_when_provider_returns_plain_text() -> None:
    result = AnswerGenerator(RunnableLambda(lambda _prompt: "일반 문자열 답변")).generate(
        get_mock_response_generation_input()
    )

    assert result.summary == "일반 문자열 답변"
    assert result.claims[0].kind == "inference"
    assert result.claims[0].evidence_ids == []
    assert result.uncertainties
