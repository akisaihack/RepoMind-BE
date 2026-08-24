"""Compact, provider-facing context models for grounded answer generation."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnswerCodeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    symbol: str | None = None
    similarity: float | None = None
    code: str


class AnswerRelationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    relation: str
    target: str


class AnswerEvidenceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    title: str
    location: str
    description: str


class AnswerGenerationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: list[AnswerCodeContext] = Field(default_factory=list)
    relations: list[AnswerRelationContext] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[AnswerEvidenceContext] = Field(default_factory=list)


__all__ = [
    "AnswerCodeContext",
    "AnswerEvidenceContext",
    "AnswerGenerationContext",
    "AnswerRelationContext",
]
