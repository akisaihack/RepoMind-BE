"""이전 대화 맥락을 참고해서 후속 질문을 독립적인 질문으로 재작성한다.

`app/ai/question_classifier.py`와 동일한 패턴 — LangChain
`llm.with_structured_output(...)`으로 구조화된 결과를 받고, 공급자 장애(429,
타임아웃 등) 시에는 예외를 삼키고 원본 질문을 그대로 반환해서 재작성 실패가
전체 검색 파이프라인을 막지 않게 한다.

배경 (docs/qa_retrieval_part_plan.md "0-14" 참고): 검색(vector_retriever의
임베딩, graph_retriever의 탐색 시작점)이 state["question"]을 그대로 쓰기
때문에, "그거 어떻게 고쳐?" 같은 후속 질문을 원문 그대로 검색하면 애초에
관련 없는 근거가 잡힌다. 답변 생성 프롬프트에만 대화 이력을 곁들이는 방식은
이미 잘못 검색된 근거를 못 고치므로, 검색 이전 단계(파이프라인 맨 앞)에서
질문 자체를 독립형으로 바꿔주는 쪽을 선택함.
"""

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from app.ai.generation.prompts import QUESTION_REWRITE_SYSTEM_PROMPT, QUESTION_REWRITE_USER_PROMPT
from app.clients.azure_openai import AZURE_OPENAI_API_VERSION
from app.dtos.question_rewrite import QuestionRewriteDecision
from app.errors import APIError

logger = logging.getLogger(__name__)


class StructuredRewriter(Protocol):
    def invoke(self, input: Any) -> QuestionRewriteDecision: ...


class QuestionRewriter:
    def __init__(self, rewriter: StructuredRewriter | None = None) -> None:
        self._rewriter = rewriter

    def rewrite(self, question: str, history: str) -> str:
        """`history`가 비어 있으면(세션의 첫 질문) LLM을 부르지 않고 원본을 그대로 반환."""
        if not history.strip():
            return question
        if self._rewriter is None:
            return question  # LLM 없이 만들어졌을 때(테스트 등) 방어적 fallback

        try:
            decision = self._rewriter.invoke(
                [
                    ("system", QUESTION_REWRITE_SYSTEM_PROMPT),
                    (
                        "human",
                        QUESTION_REWRITE_USER_PROMPT.format(history=history, question=question),
                    ),
                ]
            )
            if isinstance(decision, dict):
                decision = QuestionRewriteDecision.model_validate(decision)
            rewritten = decision.rewritten_question.strip()
            return rewritten or question
        except Exception as exc:  # 공급자 장애가 검색 파이프라인 전체를 막지 않게 함
            logger.warning("후속 질문 재작성 LLM 호출 실패, 원본 질문 사용: %s", exc)
            return question


def create_azure_question_rewriter(config: Mapping[str, Any]) -> QuestionRewriter:
    """설정에서 Azure OpenAI 기반 프로덕션 재작성기를 생성한다.

    비용/속도 때문에 nano 배포가 있으면 그걸 우선 쓰고, 없으면 일반 배포로
    대체한다 (question_classifier.py/target_selector.py와 동일한 우선순위).
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
    return QuestionRewriter(llm.with_structured_output(QuestionRewriteDecision))


__all__ = ["QuestionRewriter", "create_azure_question_rewriter"]
