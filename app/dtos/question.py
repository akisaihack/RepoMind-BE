"""Shared question classification types used across API and RAG layers."""

from enum import StrEnum


class QuestionKind(StrEnum):
    """Supported question kinds produced by the question analyzer."""

    FLOW = "flow"
    IMPACT = "impact"
    INTENT = "intent"
    LOCATION = "location"


__all__ = ["QuestionKind"]
