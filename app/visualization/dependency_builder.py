"""Extension point for dependency visualization."""

from app.dtos.response_generation import GraphResponse, ResponseGenerationInput


class DependencyBuilder:
    """Will be implemented after the dependency query result is finalized."""

    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None:
        return None
