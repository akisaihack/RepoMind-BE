"""LangChain answer generation tests with no external API calls."""

import json

from langchain_core.runnables import RunnableLambda

from app.ai.answer_generator import AnswerGenerator
from app.ai.generation.context_builder import LLMContextBuilder
from app.dtos.response_generation import QueryIntent
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
    assert "한 쌍의 백틱" in prompt_text
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
                        "citations": [
                            {
                                "content": "서비스에서 취소합니다.",
                                "evidenceIds": ["invented-id", "evidence:code:valid"],
                            }
                        ],
                    }
                ],
                "uncertainties": [],
            }
        )

    result = AnswerGenerator(RunnableLambda(answer)).generate(input_data)

    assert result.claims[0].evidence_ids == ["evidence:code:valid"]
    assert result.claims[0].citations[0].evidence_ids == ["evidence:code:valid"]


def test_answer_generator_falls_back_when_provider_returns_plain_text() -> None:
    result = AnswerGenerator(RunnableLambda(lambda _prompt: "일반 문자열 답변")).generate(
        get_mock_response_generation_input()
    )

    assert result.summary == "일반 문자열 답변"
    assert result.claims[0].kind == "inference"
    assert result.claims[0].evidence_ids == []
    assert result.uncertainties


def test_history_answer_prompt_distinguishes_facts_from_inference() -> None:
    received = []
    input_data = get_mock_response_generation_input()
    input_data.intent = QueryIntent.HISTORY
    input_data.context.history = [
        {
            "method": "AuthController.authenticateUser",
            "change_type": "modified",
            "version": {
                "node_id": "version:2",
                "method_key": "method:authenticate",
                "symbol": "AuthController.authenticateUser(LoginRequest)",
                "source_code": "validate();",
                "start_line": 20,
                "end_line": 25,
                "content_hash": "hash-2",
            },
            "commit": {
                "node_id": "commit:2",
                "sha": "def456",
                "message": "fix: 로그인 검증 추가",
                "committed_at": "2026-08-10T10:00:00Z",
            },
            "diff": {"added_lines": ["validate();"], "removed_lines": []},
        }
    ]

    def answer(prompt):
        received.append(prompt.to_string())
        return json.dumps(
            {
                "summary": "로그인 검증이 추가됐습니다.",
                "claims": [
                    {
                        "id": "claim-1",
                        "kind": "stated_intent",
                        "title": "로그인 검증 추가",
                        "content": "커밋에서 검증 코드가 추가됐습니다.",
                        "evidenceIds": [],
                        "citations": [],
                    }
                ],
                "uncertainties": [],
            },
            ensure_ascii=False,
        )

    result = AnswerGenerator(RunnableLambda(answer)).generate(input_data)

    assert result.summary == "로그인 검증이 추가됐습니다."
    assert "commit.message에 변경 이유가 명시된 경우에만" in received[0]
    assert "최초 도입 커밋이라고 단정하지 마세요" in received[0]
    assert "INTRODUCED_IN" in received[0]
    assert "HTML entity를 생성하지 마세요" in received[0]
    assert '"added_lines":["validate();"]' in received[0]
