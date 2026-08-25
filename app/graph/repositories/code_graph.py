"""Validated Neo4j persistence for source-code graph documents."""

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from neo4j import ManagedTransaction
from neo4j.exceptions import Neo4jError

from app.clients.neo4j import Neo4jClient
from app.dtos.graph import GraphDocument, GraphEdge, GraphNode

ALLOWED_NODE_LABELS = frozenset(
    {"Commit", "File", "Package", "Class", "Interface", "Method", "MethodVersion", "Endpoint"}
)
ALLOWED_RELATIONSHIP_TYPES = frozenset(
    {
        "DECLARES",
        "CONTAINS",
        "CALLS",
        "HTTP_CALLS",
        "HAS_VERSION",
        "INTRODUCED_IN",
        "DERIVED_FROM",
        "PARENT",
        "DELETED_IN",
        "EXTENDS",
        "IMPLEMENTS",
        "IMPORTS",
        "MANAGES",
        "EXPOSES",
    }
)
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
        github_repository_id: int | None = None,
        commit_hash: str | None = None,
        mark_missing_deleted: bool = True,
        resolve_introduction_history: bool = True,
    ) -> int:
        """MERGE internal graph nodes and edges; return skipped external edge count."""
        if (github_repository_id is None) != (commit_hash is None):
            raise ValueError("github_repository_id and commit_hash must be provided together.")
        nodes_by_id = self._validate_nodes(document.nodes)
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

        if not node_batches and not relationship_batches:
            return skipped_external

        def _save_in_transaction(transaction: ManagedTransaction) -> None:
            # Future repository-scoped cleanup belongs at the end of this callback so
            # graph replacement and stale-node deletion commit or roll back together.
            for label, rows in node_batches.items():
                for batch in _batches(rows, self._batch_size):
                    transaction.run(_node_query(label), rows=batch).consume()
            for labels, rows in relationship_batches.items():
                for batch in _batches(rows, self._batch_size):
                    transaction.run(
                        _relationship_query(
                            *labels,
                            resolve_introduction_history=resolve_introduction_history,
                        ),
                        rows=batch,
                    ).consume()
            if (
                mark_missing_deleted
                and github_repository_id is not None
                and commit_hash is not None
            ):
                method_keys = [node.id for node in nodes_by_id.values() if node.type == "Method"]
                transaction.run(
                    _mark_deleted_methods_query(),
                    repositoryId=github_repository_id,
                    commitKey=f"{github_repository_id}:commit:{commit_hash}",
                    activeMethodKeys=method_keys,
                ).consume()

        try:
            self._client.execute_write(_save_in_transaction)
        except Neo4jError as exc:
            raise CodeGraphPersistenceError("Failed to persist source-code graph.") from exc

        return skipped_external

    def mark_methods_deleted(
        self,
        github_repository_id: int,
        commit_hash: str,
        method_keys: list[str],
    ) -> None:
        """Record deletion only for methods proven absent in a changed file."""
        if not method_keys:
            return

        def _mark(transaction: ManagedTransaction) -> None:
            transaction.run(
                _mark_selected_methods_deleted_query(),
                repositoryId=github_repository_id,
                commitKey=f"{github_repository_id}:commit:{commit_hash}",
                methodKeys=method_keys,
            ).consume()

        try:
            self._client.execute_write(_mark)
        except Neo4jError as exc:
            raise CodeGraphPersistenceError("Failed to persist method deletion history.") from exc

    def find_method_version_at_commit(
        self,
        github_repository_id: int,
        method_key: str,
        commit_hash: str,
    ) -> Any | None:
        """Resolve the nearest version/deletion event reachable from a Commit."""
        commit_key = f"{github_repository_id}:commit:{commit_hash}"
        records, _, _ = self._client.execute_query(
            _find_method_version_at_commit_query(),
            {"methodKey": method_key, "commitKey": commit_key},
        )
        if not records or records[0]["eventType"] == "deleted":
            return None
        return records[0]["version"]

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
    return f"""
UNWIND $rows AS row
MERGE (node:{label} {{key: row.key}})
SET node += row.properties
"""


def _relationship_query(
    source_label: str,
    relationship: str,
    target_label: str,
    *,
    resolve_introduction_history: bool = True,
) -> str:
    if relationship == "INTRODUCED_IN" and resolve_introduction_history:
        return _introduced_in_query()
    return f"""
UNWIND $rows AS row
MATCH (source:{source_label} {{key: row.fromKey}})
MATCH (target:{target_label} {{key: row.toKey}})
MERGE (source)-[relation:{relationship}]->(target)
SET relation += row.properties
"""


def _introduced_in_query() -> str:
    return """
UNWIND $rows AS row
MATCH (source:MethodVersion {key: row.fromKey})
MATCH (target:Commit {key: row.toKey})
MATCH (method:Method)-[:HAS_VERSION]->(source)
WHERE NOT EXISTS {
  MATCH (source)-[:INTRODUCED_IN]->(introduced:Commit)
  WHERE EXISTS {
    MATCH (target)-[:PARENT*0..]->(introduced)
  }
  AND NOT EXISTS {
    MATCH (method)-[:DELETED_IN]->(deleted:Commit)
    WHERE EXISTS {
      MATCH (target)-[:PARENT*0..]->(deleted)
    }
    AND EXISTS {
      MATCH (deleted)-[:PARENT*0..]->(introduced)
    }
  }
}
MERGE (source)-[relation:INTRODUCED_IN]->(target)
SET relation += row.properties
"""


def _mark_deleted_methods_query() -> str:
    return """
MATCH (commit:Commit {key: $commitKey})
MATCH (method:Method {githubRepositoryId: $repositoryId})
WHERE NOT method.key IN $activeMethodKeys
  AND EXISTS { (method)-[:HAS_VERSION]->(:MethodVersion) }
  AND EXISTS {
  MATCH (method)-[:HAS_VERSION]->(:MethodVersion)-[:INTRODUCED_IN]->(introduced:Commit)
  WHERE EXISTS {
    MATCH (commit)-[:PARENT*0..]->(introduced)
  }
  AND NOT EXISTS {
    MATCH (method)-[:DELETED_IN]->(deleted:Commit)
    WHERE EXISTS {
      MATCH (commit)-[:PARENT*0..]->(deleted)
    }
    AND EXISTS {
      MATCH (deleted)-[:PARENT*0..]->(introduced)
    }
  }
  }
MERGE (method)-[:DELETED_IN]->(commit)
"""


def _mark_selected_methods_deleted_query() -> str:
    return """
MATCH (commit:Commit {key: $commitKey})
UNWIND $methodKeys AS methodKey
MATCH (method:Method {key: methodKey, githubRepositoryId: $repositoryId})
MERGE (method)-[:DELETED_IN]->(commit)
"""


def _find_method_version_at_commit_query() -> str:
    return """
MATCH (target:Commit {key: $commitKey})
MATCH (method:Method {key: $methodKey})
CALL (target, method) {
  MATCH (method)-[:HAS_VERSION]->(version:MethodVersion)-[:INTRODUCED_IN]->(introduced:Commit)
  MATCH path = (target)-[:PARENT*0..]->(introduced)
  RETURN version AS version, 'version' AS eventType, length(path) AS distance
  UNION ALL
  MATCH (method)-[:DELETED_IN]->(deleted:Commit)
  MATCH path = (target)-[:PARENT*0..]->(deleted)
  RETURN null AS version, 'deleted' AS eventType, length(path) AS distance
}
RETURN version, eventType, distance
ORDER BY distance ASC
LIMIT 1
"""
