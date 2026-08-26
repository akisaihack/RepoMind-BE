"""벡터 검색 후보 중 그래프 탐색 시작점을 선택하기 위한 DTO."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SelectionSource(StrEnum):
    EXACT_SYMBOL = "EXACT_SYMBOL"
    SINGLE_CANDIDATE = "SINGLE_CANDIDATE"
    SCORE = "SCORE"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


class TargetSelectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_index: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    reason: str


class SelectedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_node_id: str
    method_node_id: str
    path: str
    class_name: str | None = None
    method_name: str | None = None
    api_http_method: str | None = None
    api_path: str | None = None
    similarity: float
    selection_source: SelectionSource
    selection_reason: str
    confidence: float = Field(ge=0, le=1)
