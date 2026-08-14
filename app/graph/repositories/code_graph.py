"""Validated Neo4j persistence for source-code graph documents."""

from collections import defaultdict
from collections.abc import Iterable, Iterator

from neo4j import ManagedTransaction
from neo4j.exceptions import Neo4jError

from app.clients.neo4j import Neo4jClient
from app.dtos.graph import GraphDocument, GraphEdge, GraphNode

ALLOWED_NODE_LABELS = frozenset({"File", "Package", "Class", "Interface", "Method", "Endpoint"})
ALLOWED_RELATIONSHIP_TYPES = frozenset(
    {
        "DECLARES",
        "CONTAINS",
        "CALLS",
        "EXTENDS",
        "IMPLEMENTS",
        "IMPORTS",
        "MANAGES",
        "EXPOSES",
    }
)
CODE_NODE_LABELS = frozenset(ALLOWED_NODE_LABELS - {"File"})
DEFAULT_BATCH_SIZE = 1_000


class CodeGraphValidationError(ValueError):
    """Raised when a graph document contains unsupported or invalid data."""


class CodeGraphPersistenceError(Exception):
    """Raised when source-code graph persistence fails."""


class CodeGraphRepository:
    def __init__(self, client: Neo4jClient, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        if batch_size <= 0:
            raise ValueError("Code graph batch size must be positive.")
        self._client = client
        self._batch_size = batch_size

    def save(
        self,
        document: GraphDocument,
        *,
        github_repository_id: int,
        analysis_run_id: str,
    ) -> int:
        """Synchronize one repository's code graph in a managed transaction."""
        _validate_sync_identity(github_repository_id, analysis_run_id)
        nodes_by_id = self._validate_nodes(document.nodes)
        self._validate_repository_scope(nodes_by_id.values(), github_repository_id)
        internal_edges, skipped_external = self._validate_edges(document.edges, nodes_by_id)

        node_batches: dict[str, list[dict]] = defaultdict(list)
        for node in nodes_by_id.values():
            node_batches[node.type].append({"key": node.id, "properties": dict(node.properties)})

        relationship_batches: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for edge in internal_edges:
            source_label = nodes_by_id[edge.source].type
            target_label = nodes_by_id[edge.target].type
            relationship_batches[(source_label, edge.type, target_label)].append(
                {
                    "fromKey": edge.source,
                    "toKey": edge.target,
                    "properties": dict(edge.properties),
                }
            )

        def _save_in_transaction(transaction: ManagedTransaction) -> None:
            for label, rows in node_batches.items():
                for batch in _batches(rows, self._batch_size):
                    transaction.run(
                        _node_query(label),
                        rows=batch,
                        analysisRunId=analysis_run_id,
                    ).consume()
            for labels, rows in relationship_batches.items():
                for batch in _batches(rows, self._batch_size):
                    transaction.run(
                        _relationship_query(*labels),
                        rows=batch,
                        analysisRunId=analysis_run_id,
                    ).consume()
            transaction.run(
                _DELETE_STALE_CODE_RELATIONSHIPS,
                repositoryId=github_repository_id,
                analysisRunId=analysis_run_id,
                relationshipTypes=sorted(ALLOWED_RELATIONSHIP_TYPES),
            ).consume()
            transaction.run(
                _DELETE_STALE_CODE_NODES,
                repositoryId=github_repository_id,
                analysisRunId=analysis_run_id,
            ).consume()

        try:
            self._client.execute_write(_save_in_transaction)
        except Neo4jError as exc:
            raise CodeGraphPersistenceError("Failed to persist source-code graph.") from exc

        return skipped_external

    @staticmethod
    def _validate_nodes(nodes: tuple[GraphNode, ...]) -> dict[str, GraphNode]:
        nodes_by_id: dict[str, GraphNode] = {}
        for node in nodes:
            if node.type not in ALLOWED_NODE_LABELS:
                raise CodeGraphValidationError(f"Unsupported graph node label: {node.type!r}.")
            if not isinstance(node.id, str) or not node.id:
                raise CodeGraphValidationError("Graph node key must be non-empty.")
            existing = nodes_by_id.get(node.id)
            if existing is not None and existing != node:
                raise CodeGraphValidationError(f"Conflicting graph nodes share key {node.id!r}.")
            nodes_by_id[node.id] = node
        return nodes_by_id

    @staticmethod
    def _validate_repository_scope(nodes: Iterable[GraphNode], github_repository_id: int) -> None:
        for node in nodes:
            if node.properties.get("githubRepositoryId") != github_repository_id:
                raise CodeGraphValidationError(
                    f"Graph node {node.id!r} is outside repository {github_repository_id}."
                )

    @staticmethod
    def _validate_edges(
        edges: tuple[GraphEdge, ...], nodes_by_id: dict[str, GraphNode]
    ) -> tuple[list[GraphEdge], int]:
        internal: list[GraphEdge] = []
        skipped_external = 0
        for edge in edges:
            if edge.type not in ALLOWED_RELATIONSHIP_TYPES:
                raise CodeGraphValidationError(
                    f"Unsupported graph relationship type: {edge.type!r}."
                )
            if not edge.source or not edge.target:
                raise CodeGraphValidationError("Graph relationship endpoints must be non-empty.")
            if edge.properties.get("external") is True:
                skipped_external += 1
                continue
            if edge.source not in nodes_by_id or edge.target not in nodes_by_id:
                raise CodeGraphValidationError(
                    f"Graph relationship {edge.type!r} references a missing internal node."
                )
            internal.append(edge)
        return internal, skipped_external


def _batches(rows: list[dict], batch_size: int) -> Iterator[list[dict]]:
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


def _node_query(label: str) -> str:
    run_marker = "SET node.analysisRunId = $analysisRunId" if label in CODE_NODE_LABELS else ""
    return f"""
UNWIND $rows AS row
MERGE (node:{label} {{key: row.key}})
SET node += row.properties
{run_marker}
"""


def _relationship_query(source_label: str, relationship: str, target_label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (source:{source_label} {{key: row.fromKey}})
MATCH (target:{target_label} {{key: row.toKey}})
MERGE (source)-[relation:{relationship}]->(target)
SET relation += row.properties
SET relation.analysisRunId = $analysisRunId
"""


_DELETE_STALE_CODE_RELATIONSHIPS = """
MATCH (source)-[relation]->(target)
WHERE type(relation) IN $relationshipTypes
  AND (
    source.githubRepositoryId = $repositoryId
    OR target.githubRepositoryId = $repositoryId
  )
  AND (
    relation.analysisRunId IS NULL
    OR relation.analysisRunId <> $analysisRunId
  )
DELETE relation
"""

_DELETE_STALE_CODE_NODES = """
MATCH (node)
WHERE (node:Package OR node:Class OR node:Interface OR node:Method OR node:Endpoint)
  AND node.githubRepositoryId = $repositoryId
  AND (
    node.analysisRunId IS NULL
    OR node.analysisRunId <> $analysisRunId
  )
DETACH DELETE node
"""


def _validate_sync_identity(github_repository_id: int, analysis_run_id: str) -> None:
    if (
        not isinstance(github_repository_id, int)
        or isinstance(github_repository_id, bool)
        or github_repository_id <= 0
    ):
        raise CodeGraphValidationError("GitHub repository ID must be a positive integer.")
    if not isinstance(analysis_run_id, str) or not analysis_run_id.strip():
        raise CodeGraphValidationError("Analysis run ID must be non-empty.")
