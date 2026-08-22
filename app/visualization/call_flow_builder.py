"""Build a React Flow compatible call graph from normalized DB relations."""

import logging
from collections.abc import Mapping
from typing import Any

from app.dtos.response_generation import (
    GraphEdge,
    GraphNode,
    GraphResponse,
    ResponseGenerationInput,
    VisualizationType,
)

logger = logging.getLogger(__name__)


class CallFlowBuilder:
    """Convert source/relation/target rows without inventing graph entities."""

    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None:
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}

        for row in input_data.context.graph:
            source = row.get("source")
            target = row.get("target")
            relation = row.get("relation")
            if not isinstance(source, Mapping) or not isinstance(target, Mapping):
                logger.warning("Skipping graph row with missing endpoints")
                continue
            if not isinstance(relation, str) or not relation:
                logger.warning("Skipping graph row with missing relation")
                continue

            source_node = self._node_from(source)
            target_node = self._node_from(target)
            if source_node is None or target_node is None:
                logger.warning("Skipping graph row with invalid endpoint data")
                continue

            nodes.setdefault(source_node.id, source_node)
            nodes.setdefault(target_node.id, target_node)
            edge_id = f"{source_node.id}:{relation}:{target_node.id}"
            edges.setdefault(
                edge_id,
                GraphEdge(
                    id=edge_id,
                    source=source_node.id,
                    target=target_node.id,
                    type=relation,
                    label=relation,
                ),
            )

        if not nodes:
            return None
        return GraphResponse(
            type=VisualizationType.CALL_FLOW,
            nodes=list(nodes.values()),
            edges=list(edges.values()),
        )

    @staticmethod
    def _node_from(value: Mapping[str, Any]) -> GraphNode | None:
        node_id = value.get("id")
        name = value.get("name")
        node_type = value.get("type")
        if not all(isinstance(item, str) and item for item in (node_id, name, node_type)):
            return None

        metadata = value.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        label = name if name.endswith(")") else f"{name}()"
        return GraphNode(id=node_id, type=node_type, label=label, metadata=metadata)
