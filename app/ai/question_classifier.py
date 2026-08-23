"""사용자 질문을 flow/impact/intent/location 4가지 유형 중 하나로 분류한다.

`app/ai/target_selector.py`와 동일한 패턴 — LangChain
`llm.with_structured_output(...)`으로 구조화된 결과를 받고, 공급자 장애(429,
타임아웃 등) 시에는 예외를 삼키고 `QuestionKind.LOCATION`으로 폴백해서
질문 분류 실패가 전체 파이프라인을 막지 않게 한다.
"""

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from app.ai.generation.prompts import QUESTION_CLASSIFICATION_PROMPT
from app.clients.azure_openai import AZURE_OPENAI_API_VERSION
from app.dtos.question import QuestionClassificationDecision, QuestionKind
from app.errors import APIError

logger = logging.getLogger(__name__)


class StructuredClassifier(Protocol):
    def invoke(self, input: Any) -> QuestionClassificationDecision: ...


class QuestionClassifier:
    def __init__(self, classifier: StructuredClassifier | None = None) -> None:
        self._classifier = classifier

    def classify(self, question: str) -> QuestionKind:
        if self._classifier is None:
            return QuestionKind.LOCATION  # LLM 없이 만들어졌을 때(테스트 등) 방어적 fallback

        try:
            decision = self._classifier.invoke(
                [
                    ("system", QUESTION_CLASSIFICATION_PROMPT),
                    ("human", question),
                ]
            )
            if isinstance(decision, dict):
                decision = QuestionClassificationDecision.model_validate(decision)
            return decision.question_kind
        except Exception as exc:  # 공급자 장애가 검색 파이프라인 전체를 막지 않게 함
            logger.warning("질문 분류 LLM 호출 실패, location으로 폴백: %s", exc)
            return QuestionKind.LOCATION


def create_azure_question_classifier(config: Mapping[str, Any]) -> QuestionClassifier:
    """설정에서 Azure OpenAI 기반 프로덕션 분류기를 생성한다.

    비용/속도 때문에 nano 배포가 있으면 그걸 우선 쓰고, 없으면 일반 배포로
    대체한다 (target_selector.py와 동일한 우선순위).
    """
    deployment = config.get("AZURE_OPENAI_NANO_DEPLOYMENT") or config.get(
        "AZURE_OPENAI_DEPLOYMENT"
    )
    required = {
        "AZURE_OPENAI_ENDPOINT": config.get("AZURE_OPENAI_ENDPOINT"),
        "AZURE_OPENAI_API_KEY": config.get("AZURE_OPENAI_API_KEY"),
        "deployment": deployment,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise APIError(
            "AZURE_OPENAI_CONFIGURATION_ERROR",
            f"Missing required Azure OpenAI configuration: {', '.join(missing)}.",
            status=500,
        )

    # Imported lazily so pure builder/unit-test paths do not initialize a provider SDK.
    from langchain_openai import AzureChatOpenAI

    llm = AzureChatOpenAI(
        azure_endpoint=config["AZURE_OPENAI_ENDPOINT"],
        api_key=config["AZURE_OPENAI_API_KEY"],
        azure_deployment=deployment,
        api_version=AZURE_OPENAI_API_VERSION,
        temperature=0,
    )
    return QuestionClassifier(llm.with_structured_output(QuestionClassificationDecision))


__all__ = ["QuestionClassifier", "create_azure_question_classifier"]
