"""Grounded natural-language answer generation through LangChain."""

import json
import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.ai.generation.context_builder import LLMContextBuilder
from app.ai.generation.prompts import (
    RESPONSE_INTENT_INSTRUCTIONS,
    RESPONSE_SYSTEM_PROMPT,
    RESPONSE_USER_PROMPT,
)
from app.clients.azure_openai import AZURE_OPENAI_API_VERSION
from app.dtos.response_generation import (
    GeneratedAnswer,
    GeneratedCitation,
    GeneratedClaim,
    ResponseGenerationInput,
)
from app.errors import APIError

logger = logging.getLogger(__name__)


class AnswerGenerationError(Exception):
    """Raised when the configured language model cannot generate an answer."""


class AnswerGenerator:
    def __init__(
        self,
        llm: BaseLanguageModel | Runnable[Any, Any],
        context_builder: LLMContextBuilder | None = None,
    ) -> None:
        prompt = ChatPromptTemplate.from_messages(
            [("system", RESPONSE_SYSTEM_PROMPT), ("human", RESPONSE_USER_PROMPT)]
        )
        self._chain = prompt | llm | StrOutputParser()
        self._context_builder = context_builder or LLMContextBuilder()

    def generate(self, input_data: ResponseGenerationInput) -> GeneratedAnswer:
        """Generate structured answer content; visualization remains deterministic."""
        context = self._context_builder.build(input_data)
        try:
            answer = self._invoke(input_data, context)
        except Exception as exc:
            if not _is_provider_limit_error(exc):
                raise AnswerGenerationError("The answer provider request failed.") from exc

            original_size = self._context_builder.size(context)
            fallback = self._context_builder.build_fallback(input_data, original_size)
            fallback_size = self._context_builder.size(fallback)
            if fallback_size >= original_size:
                raise AnswerGenerationError("The answer provider request failed.") from exc
            logger.warning(
                "Answer provider limit reached; retrying with reduced context: %d -> %d chars",
                original_size,
                fallback_size,
            )
            try:
                answer = self._invoke(input_data, fallback)
            except Exception as retry_exc:
                raise AnswerGenerationError("The answer provider request failed.") from retry_exc

        if not answer:
            raise AnswerGenerationError("The answer provider returned an empty response.")
        return _parse_and_validate_answer(answer, context.evidence)

    def _invoke(self, input_data: ResponseGenerationInput, context: Any) -> str:
        values = {
            "question": input_data.question,
            "intent": input_data.intent.value,
            "target": input_data.target or "지정되지 않음",
            "intent_instruction": RESPONSE_INTENT_INSTRUCTIONS[input_data.intent],
            "code_context": _serialize(context.code),
            "graph_context": _serialize(context.relations),
            "history_context": _serialize(context.history),
            "evidence_context": _serialize(context.evidence),
        }
        return self._chain.invoke(values).strip()


def _parse_and_validate_answer(raw_answer: str, evidence: list[Any]) -> GeneratedAnswer:
    allowed_evidence_ids = {item.id for item in evidence}
    try:
        parsed = GeneratedAnswer.model_validate_json(_strip_json_fence(raw_answer))
    except Exception:
        logger.warning("Answer provider returned non-structured output; using safe fallback.")
        return GeneratedAnswer(
            summary=raw_answer.strip(),
            claims=[
                GeneratedClaim(
                    id="claim-1",
                    kind="inference",
                    title="답변",
                    content=raw_answer.strip(),
                    evidenceIds=[],
                )
            ],
            uncertainties=["구조화된 답변을 생성하지 못해 근거 연결을 확인할 수 없습니다."],
        )

    claims: list[GeneratedClaim] = []
    seen_claim_ids: set[str] = set()
    for index, claim in enumerate(parsed.claims, start=1):
        claim_id = claim.id.strip()
        if not claim_id or claim_id in seen_claim_ids:
            claim_id = f"claim-{index}"
        seen_claim_ids.add(claim_id)
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for evidence_id in claim.evidence_ids
                if evidence_id in allowed_evidence_ids
            )
        )
        claims.append(
            claim.model_copy(
                update={
                    "id": claim_id,
                    "evidence_ids": evidence_ids,
                    "citations": [
                        GeneratedCitation(
                            content=citation.content,
                            evidenceIds=list(
                                dict.fromkeys(
                                    evidence_id
                                    for evidence_id in citation.evidence_ids
                                    if evidence_id in allowed_evidence_ids
                                )
                            ),
                        )
                        for citation in claim.citations
                        if citation.content.strip()
                    ],
                },
            )
        )
    return parsed.model_copy(update={"claims": claims})


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _serialize(value: list[Any]) -> str:
    if not value:
        return "조회 결과 없음"
    serializable = [
        item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else item
        for item in value
    ]
    return json.dumps(serializable, ensure_ascii=False, default=str, separators=(",", ":"))


def _is_provider_limit_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        status_code = getattr(current, "status_code", None)
        code = str(getattr(current, "code", "")).lower()
        message = str(current).lower()
        if status_code == 429 or code in {"rate_limit_exceeded", "context_length_exceeded"}:
            return True
        if "context_length_exceeded" in message or "maximum context length" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def create_azure_answer_generator(config: Mapping[str, Any]) -> AnswerGenerator:
    """Construct the production LangChain Azure chat model from application config."""
    required_keys = (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
    )
    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        raise APIError(
            "AZURE_OPENAI_CONFIGURATION_ERROR",
            f"Missing required Azure OpenAI configuration: {', '.join(missing_keys)}.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    # Imported lazily so pure builder/unit-test paths do not initialize a provider SDK.
    from langchain_openai import AzureChatOpenAI

    llm = AzureChatOpenAI(
        azure_endpoint=config["AZURE_OPENAI_ENDPOINT"],
        api_key=config["AZURE_OPENAI_API_KEY"],
        azure_deployment=config["AZURE_OPENAI_DEPLOYMENT"],
        api_version=AZURE_OPENAI_API_VERSION,
        temperature=0,
    )
    return AnswerGenerator(llm)


__all__ = [
    "AnswerGenerationError",
    "AnswerGenerator",
    "create_azure_answer_generator",
]
