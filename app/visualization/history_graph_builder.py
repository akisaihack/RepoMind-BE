"""Extension point for change-history visualization."""

from app.dtos.response_generation import GraphResponse, ResponseGenerationInput


class ChangeHistoryBuilder:
    """Will be implemented after the history query result is finalized."""

    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None:
        return None
