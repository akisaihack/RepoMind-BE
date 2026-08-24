"""Build a connected React Flow call graph from retrieval relations."""

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

_CALL_RELATIONS = {"CALLS", "HTTP_CALLS"}
_METHOD_VERSION_RELATION = "HAS_VERSION"
_ENDPOINT_RELATION = "EXPOSES"


class CallFlowBuilder:
    """Project graph internals into only connected, user-visible call paths."""

    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None:
        relations = _valid_relations(input_data.context.graph)
        method_by_version = _method_by_version(relations)
        call_edges = self._call_edges(relations, method_by_version)
        if not call_edges:
            logger.info("No CALLS relation available for flow visualization")
            return None

        connected_method_ids = {
            node_id for edge in call_edges.values() for node_id in (edge.source, edge.target)
        }
        endpoint_edges = self._endpoint_edges(relations, connected_method_ids)
        edges = {**endpoint_edges, **call_edges}
        nodes = self._nodes_for_edges(relations, edges)
        if not nodes:
            return None
        return GraphResponse(
            type=VisualizationType.CALL_FLOW,
            nodes=list(nodes.values()),
            edges=list(edges.values()),
        )

    def _call_edges(
        self,
        relations: list[dict[str, Any]],
        method_by_version: dict[str, Mapping[str, Any]],
    ) -> dict[str, GraphEdge]:
        edges: dict[str, GraphEdge] = {}
        for row in relations:
            relation = row["relation"].upper()
            if relation not in _CALL_RELATIONS:
                continue
            source = method_by_version.get(row["source"]["id"], row["source"])
            target = method_by_version.get(row["target"]["id"], row["target"])
            source_node = self._node_from(source)
            target_node = self._node_from(target)
            if source_node is None or target_node is None:
                continue
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
        return edges

    def _endpoint_edges(
        self,
        relations: list[dict[str, Any]],
        connected_method_ids: set[str],
    ) -> dict[str, GraphEdge]:
        edges: dict[str, GraphEdge] = {}
        for row in relations:
            if row["relation"].upper() != _ENDPOINT_RELATION:
                continue
            method = self._node_from(row["source"])
            endpoint = self._node_from(row["target"])
            if method is None or endpoint is None or method.id not in connected_method_ids:
                continue
            edge_id = f"{endpoint.id}:HANDLED_BY:{method.id}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                source=endpoint.id,
                target=method.id,
                type="HANDLED_BY",
                label="HANDLED_BY",
            )
        return edges

    def _nodes_for_edges(
        self, relations: list[dict[str, Any]], edges: dict[str, GraphEdge]
    ) -> dict[str, GraphNode]:
        referenced_ids = {
            node_id
            for edge in edges.values()
            for node_id in (edge.source, edge.target)
        }
        nodes: dict[str, GraphNode] = {}
        for row in relations:
            for value in (row["source"], row["target"]):
                node = self._node_from(value)
                if node is not None and node.id in referenced_ids:
                    nodes.setdefault(node.id, node)
        return nodes

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
        label = name if name.endswith(")") or node_type.upper() == "API" else f"{name}()"
        return GraphNode(id=node_id, type=node_type, label=label, metadata=metadata)


def _valid_relations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for row in rows:
        source = row.get("source")
        target = row.get("target")
        relation = row.get("relation")
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            logger.warning("Skipping graph row with missing endpoints")
            continue
        if not isinstance(relation, str) or not relation:
            logger.warning("Skipping graph row with missing relation")
            continue
        if not isinstance(source.get("id"), str) or not isinstance(target.get("id"), str):
            logger.warning("Skipping graph row with invalid endpoint IDs")
            continue
        valid.append({"source": source, "target": target, "relation": relation})
    return valid


def _method_by_version(relations: list[dict[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Map MethodVersion IDs to their stable Method nodes for flow projection."""
    versions: dict[str, Mapping[str, Any]] = {}
    for row in relations:
        if row["relation"].upper() == _METHOD_VERSION_RELATION:
            versions[row["target"]["id"]] = row["source"]
    return versions
