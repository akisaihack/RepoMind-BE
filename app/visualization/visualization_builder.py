"""Select a deterministic graph builder for the requested visualization."""

import logging

from app.dtos.response_generation import (
    GraphResponse,
    ResponseGenerationInput,
    VisualizationType,
)
from app.visualization.base import GraphTypeBuilder
from app.visualization.call_flow_builder import CallFlowBuilder

logger = logging.getLogger(__name__)


class VisualizationBuilder:
    def __init__(self, builders: dict[VisualizationType, GraphTypeBuilder] | None = None) -> None:
        self._builders = builders or {VisualizationType.CALL_FLOW: CallFlowBuilder()}

    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None:
        if not input_data.visualization_required:
            return None
        if not input_data.context.graph:
            logger.info("Visualization requested without graph context")
            return None
        if input_data.visualization_type is None:
            logger.warning("Visualization requested without a visualization type")
            return None

        builder = self._builders.get(input_data.visualization_type)
        if builder is None:
            logger.warning(
                "Unsupported visualization type: %s", input_data.visualization_type.value
            )
            return None
        return builder.build(input_data)
