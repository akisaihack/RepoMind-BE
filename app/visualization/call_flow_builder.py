"""Build a connected React Flow call graph from retrieval relations."""

import logging
from collections import deque
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
_MAX_FLOW_NODES = 10
_SEMANTIC_ACCESSOR_TERMS = ("jwt", "token", "authorization")


class CallFlowBuilder:
    """Project graph internals into only connected, user-visible call paths."""

    def build(self, input_data: ResponseGenerationInput) -> GraphResponse | None:
        relations = _valid_relations(input_data.context.graph)
        method_by_version = _method_by_version(relations)
        call_edges = self._call_edges(relations, method_by_version)
        if not call_edges:
            logger.info("No CALLS relation available for flow visualization")
            return None
        nodes_by_id = self._nodes_by_id(relations)
        connected_method_ids = {
            node_id for edge in call_edges.values() for node_id in (edge.source, edge.target)
        }
        endpoint_edges = self._endpoint_edges(relations, connected_method_ids)
        edges = self._select_primary_path(
            {**call_edges, **endpoint_edges},
            nodes_by_id,
            target=input_data.target,
        )
        if not any(edge.type in _CALL_RELATIONS for edge in edges.values()):
            logger.info("No meaningful CALLS relation available for flow visualization")
            return None
        nodes = self._nodes_for_edges(relations, edges)
        if not nodes:
            return None
        return GraphResponse(
            type=VisualizationType.CALL_FLOW,
            nodes=list(nodes.values()),
            edges=list(edges.values()),
        )

    def _select_primary_path(
        self,
        call_edges: dict[str, GraphEdge],
        nodes_by_id: Mapping[str, GraphNode],
        *,
        target: str | None,
    ) -> dict[str, GraphEdge]:
        """Keep one compact, explainable call path instead of every reachable branch.

        Graph retrieval follows all outgoing CALLS relations. That is useful for
        search, but visualizing every branch makes framework DTO accessors drown
        out the requested flow. We remove trivial accessors, pick the selected
        root, then retain a bounded BFS tree whose semantic operations win ties.
        """
        meaningful_edges = {
            edge_id: edge
            for edge_id, edge in call_edges.items()
            if not _is_trivial_accessor(nodes_by_id.get(edge.target))
        }
        if not meaningful_edges:
            return {}

        sources = {edge.source for edge in meaningful_edges.values()}
        targets = {edge.target for edge in meaningful_edges.values()}
        roots = sources - targets
        if not roots:
            roots = sources
        root = max(
            roots,
            key=lambda node_id: _root_priority(nodes_by_id.get(node_id), target),
        )

        outgoing: dict[str, list[tuple[str, GraphEdge]]] = {}
        for edge in meaningful_edges.values():
            outgoing.setdefault(edge.source, []).append((edge.target, edge))
            # API endpoint is an entry point to its controller. It must also
            # be reachable while walking from the controller-rooted flow.
            if edge.type == "HANDLED_BY":
                outgoing.setdefault(edge.target, []).append((edge.source, edge))
        for edges in outgoing.values():
            edges.sort(
                key=lambda item: _node_priority(nodes_by_id.get(item[0])),
                reverse=True,
            )

        selected_nodes = {root}
        selected_edges: dict[str, GraphEdge] = {}
        queue = deque([root])
        while queue and len(selected_nodes) < _MAX_FLOW_NODES:
            source = queue.popleft()
            for next_node, edge in outgoing.get(source, []):
                if next_node in selected_nodes:
                    continue
                selected_nodes.add(next_node)
                selected_edges[edge.id] = edge
                queue.append(next_node)
                if len(selected_nodes) >= _MAX_FLOW_NODES:
                    break

        return selected_edges

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

    def _nodes_by_id(self, relations: list[dict[str, Any]]) -> dict[str, GraphNode]:
        nodes: dict[str, GraphNode] = {}
        for row in relations:
            for value in (row["source"], row["target"]):
                node = self._node_from(value)
                if node is not None:
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


def _is_trivial_accessor(node: GraphNode | None) -> bool:
    if node is None:
        return False
    method_name = node.label.rsplit(".", 1)[-1].split("(", 1)[0]
    is_accessor = method_name.startswith(("get", "set", "is")) and len(method_name) > 3
    if not is_accessor:
        return False
    return not any(term in node.label.lower() for term in _SEMANTIC_ACCESSOR_TERMS)


def _node_priority(node: GraphNode | None) -> int:
    if node is None:
        return 0
    label = node.label.lower()
    score = 0
    if any(term in label for term in ("jwt", "token", "auth", "security", "filter")):
        score += 4
    operation_terms = ("validate", "parse", "load", "find", "create", "save", "set")
    if any(term in label for term in operation_terms):
        score += 2
    return score


def _root_priority(node: GraphNode | None, target: str | None) -> int:
    score = _node_priority(node)
    if node is not None and target and target.lower() in node.label.lower():
        score += 10
    return score
