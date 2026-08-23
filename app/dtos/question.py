"""Shared question classification types used across API and RAG layers."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class QuestionKind(StrEnum):
    """Supported question kinds produced by the question analyzer."""

    FLOW = "flow"
    IMPACT = "impact"
    INTENT = "intent"
    LOCATION = "location"


class QuestionClassificationDecision(BaseModel):
    """LLM structured-output shape for `question_analyzer.py` (Step 7).

    `target_selection.py`의 `TargetSelectionDecision`과 동일한 패턴 —
    `llm.with_structured_output(QuestionClassificationDecision)`로 씀.
    """

    model_config = ConfigDict(extra="forbid")

    question_kind: QuestionKind
    reason: str


__all__ = ["QuestionClassificationDecision", "QuestionKind"]
