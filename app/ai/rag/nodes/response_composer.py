"""Compose the final grounded answer and optional visualization."""

from flask import current_app

from app.adapters.response_input_adapter import ResponseInputAdapter
from app.ai.answer_generator import create_azure_answer_generator
from app.ai.rag.state import QAState
from app.services.response_service import ResponseService
from app.visualization.visualization_builder import VisualizationBuilder


def compose_answer(
    state: QAState,
    response_service: ResponseService | None = None,
) -> dict:
    """Convert retrieval state and store a JSON-compatible QueryResponse in the state."""
    service = response_service or _create_response_service()
    input_data = ResponseInputAdapter().adapt_qa_state(state)
    response = service.generate(input_data)
    return {"answer": response.model_dump(mode="json")}


def _create_response_service() -> ResponseService:
    """Create production response dependencies from the active Flask application."""
    return ResponseService(
        answer_generator=create_azure_answer_generator(current_app.config),
        visualization_builder=VisualizationBuilder(),
    )


__all__ = ["compose_answer"]
