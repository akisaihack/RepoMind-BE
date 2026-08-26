"""질문과 가장 잘 맞는 그래프 탐색 시작점을 벡터 후보에서 선택한다."""

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from app.ai.generation.prompts import TARGET_SELECTION_SYSTEM_PROMPT, TARGET_SELECTION_USER_PROMPT
from app.ai.rag.state import VectorHit
from app.clients.azure_openai import AZURE_OPENAI_API_VERSION
from app.dtos.target_selection import (
    SelectedTarget,
    SelectionSource,
    TargetSelectionDecision,
)
from app.errors import APIError

logger = logging.getLogger(__name__)

CLEAR_SCORE_GAP = 0.05
MAX_SELECTION_CANDIDATES = 5
MAX_CODE_EXCERPT_CHARS = 800


class StructuredSelector(Protocol):
    def invoke(self, input: Any) -> TargetSelectionDecision: ...


class TargetSelector:
    def __init__(self, selector: StructuredSelector | None = None) -> None:
        self._selector = selector

    def select(
        self,
        question: str,
        candidates: list[VectorHit],
        *,
        exact_candidates: list[VectorHit] | None = None,
        symbol_names: list[str] | None = None,
    ) -> SelectedTarget | None:
        if exact_candidates:
            candidate = _best_exact_candidate(exact_candidates, symbol_names or [])
            return _selected(
                candidate,
                SelectionSource.EXACT_SYMBOL,
                "질문에서 식별한 코드 심볼과 정확히 일치",
                1,
            )
        if not candidates:
            return None
        if len(candidates) == 1:
            return _selected(candidates[0], SelectionSource.SINGLE_CANDIDATE, "단일 후보", 1)

        score_gap = candidates[0]["similarity"] - candidates[1]["similarity"]
        if score_gap >= CLEAR_SCORE_GAP:
            return _selected(
                candidates[0], SelectionSource.SCORE, f"유사도 차이 {score_gap:.4f}", 1
            )

        if self._selector is None:
            return _fallback(candidates[0], "LLM 선택기를 사용할 수 없음")

        shortlist = candidates[:MAX_SELECTION_CANDIDATES]
        try:
            decision = self._selector.invoke(
                [
                    ("system", TARGET_SELECTION_SYSTEM_PROMPT),
                    (
                        "human",
                        TARGET_SELECTION_USER_PROMPT.format(
                            question=question,
                            candidates=_format_candidates(shortlist),
                        ),
                    ),
                ]
            )
            if isinstance(decision, dict):
                decision = TargetSelectionDecision.model_validate(decision)
            if decision.selected_index >= len(shortlist):
                raise ValueError("selected_index가 후보 범위를 벗어남")
            return _selected(
                shortlist[decision.selected_index],
                SelectionSource.LLM,
                decision.reason,
                decision.confidence,
            )
        except Exception as exc:  # 공급자 장애가 검색 파이프라인 전체를 막지 않게 함
            logger.warning("분석 대상 LLM 선택 실패, 벡터 1위 사용: %s", exc)
            return _fallback(candidates[0], f"LLM 선택 실패: {type(exc).__name__}")


def create_azure_target_selector(config: Mapping[str, Any]) -> TargetSelector:
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

    from langchain_openai import AzureChatOpenAI

    llm = AzureChatOpenAI(
        azure_endpoint=config["AZURE_OPENAI_ENDPOINT"],
        api_key=config["AZURE_OPENAI_API_KEY"],
        azure_deployment=deployment,
        api_version=AZURE_OPENAI_API_VERSION,
        temperature=0,
    )
    return TargetSelector(llm.with_structured_output(TargetSelectionDecision))


def _format_candidates(candidates: list[VectorHit]) -> str:
    blocks = []
    for index, candidate in enumerate(candidates):
        endpoint = " ".join(
            value
            for value in (candidate.get("api_http_method"), candidate.get("api_path"))
            if value
        ) or "없음"
        blocks.append(
            f"[{index}] {candidate.get('class_name')}.{candidate.get('method_name')}\n"
            f"파일: {candidate.get('path')}\n엔드포인트: {endpoint}\n"
            f"유사도: {candidate['similarity']:.4f}\n"
            f"코드:\n{candidate.get('text', '')[:MAX_CODE_EXCERPT_CHARS]}"
        )
    return "\n\n".join(blocks)


def _selected(
    candidate: VectorHit,
    source: SelectionSource,
    reason: str,
    confidence: float,
) -> SelectedTarget:
    return SelectedTarget(
        **{key: candidate.get(key) for key in (
            "graph_node_id", "method_node_id", "path", "class_name", "method_name",
            "api_http_method", "api_path", "similarity"
        )},
        selection_source=source,
        selection_reason=reason,
        confidence=confidence,
    )


def _fallback(candidate: VectorHit, reason: str) -> SelectedTarget:
    return _selected(candidate, SelectionSource.FALLBACK, reason, 0)


def _best_exact_candidate(
    candidates: list[VectorHit], symbol_names: list[str]
) -> VectorHit:
    priority = {name: len(symbol_names) - index for index, name in enumerate(symbol_names)}

    def score(candidate: VectorHit) -> tuple[int, int, float]:
        method_score = priority.get(candidate.get("method_name") or "", 0)
        class_score = priority.get(candidate.get("class_name") or "", 0)
        text = candidate.get("text", "")
        supporting_names = sum(name in text for name in symbol_names)
        return (method_score * 2 + class_score, supporting_names, candidate["similarity"])

    return max(candidates, key=score)
