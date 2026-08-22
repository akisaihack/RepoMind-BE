"""Visualization builder contract."""

from typing import Protocol

from app.dtos.response_generation import GraphResponse, ResponseGenerationInput


class GraphTypeBuilder(Protocol):
    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None: ...
