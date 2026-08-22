"""Internal input and public output models for response generation."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryIntent(StrEnum):
    FLOW = "FLOW"
    DEPENDENCY = "DEPENDENCY"
    HISTORY = "HISTORY"
    EXPLANATION = "EXPLANATION"


class VisualizationType(StrEnum):
    CALL_FLOW = "CALL_FLOW"
    DEPENDENCY = "DEPENDENCY"
    CHANGE_HISTORY = "CHANGE_HISTORY"


class RetrievedContext(BaseModel):
    """Normalized retrieval output, independent of any upstream DTO."""

    model_config = ConfigDict(extra="forbid")

    code: list[dict[str, Any]] = Field(default_factory=list)
    graph: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)


class ResponseGenerationInput(BaseModel):
    """Stable boundary between retrieval and response generation."""

    model_config = ConfigDict(extra="forbid")

    question: str
    intent: QueryIntent
    target: str | None = None
    visualization_required: bool = False
    visualization_type: VisualizationType | None = None
    context: RetrievedContext

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value.strip()


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    type: str
    label: str | None = None


class GraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: VisualizationType
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    intent: QueryIntent
    visualization: GraphResponse | None = None


__all__ = [
    "GraphEdge",
    "GraphNode",
    "GraphResponse",
    "QueryIntent",
    "QueryResponse",
    "ResponseGenerationInput",
    "RetrievedContext",
    "VisualizationType",
]
