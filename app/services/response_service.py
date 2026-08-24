"""Orchestrate grounded answer and deterministic visualization generation."""

from http import HTTPStatus

from app.ai.answer_generator import AnswerGenerationError, AnswerGenerator
from app.dtos.response_generation import (
    QueryResponse,
    ResponseGenerationInput,
)
from app.errors import APIError
from app.visualization.visualization_builder import VisualizationBuilder


class ResponseService:
    def __init__(
        self,
        answer_generator: AnswerGenerator,
        visualization_builder: VisualizationBuilder,
    ) -> None:
        self._answer_generator = answer_generator
        self._visualization_builder = visualization_builder

    def generate(self, input_data: ResponseGenerationInput) -> QueryResponse:
        try:
            generated = self._answer_generator.generate(input_data)
        except AnswerGenerationError as exc:
            raise APIError(
                "ANSWER_PROVIDER_ERROR",
                "The answer provider request failed.",
                status=HTTPStatus.BAD_GATEWAY,
            ) from exc

        visualization = self._visualization_builder.build(input_data)
        return QueryResponse(
            answer=generated.summary,
            intent=input_data.intent,
            visualization=visualization,
            claims=generated.claims,
            uncertainties=generated.uncertainties,
        )


def generate_response(
    input_data: ResponseGenerationInput,
    *,
    answer_generator: AnswerGenerator,
    visualization_builder: VisualizationBuilder | None = None,
) -> QueryResponse:
    """Convenience entry point whose dependencies remain explicit and testable."""
    service = ResponseService(
        answer_generator=answer_generator,
        visualization_builder=visualization_builder or VisualizationBuilder(),
    )
    return service.generate(input_data)


__all__ = ["ResponseService", "generate_response"]
