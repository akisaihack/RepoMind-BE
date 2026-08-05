"""Neo4j persistence for normalized GitHub development history."""

from neo4j.exceptions import Neo4jError

from app.clients.neo4j import Neo4jClient
from app.graph.models import GitHubGraphData, GraphRow


class GraphPersistenceError(Exception):
    """Raised when GitHub graph persistence fails."""


class GitHubHistoryGraphRepository:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    def save(self, data: GitHubGraphData) -> None:
        """MERGE graph batches so importing the same repository is idempotent."""
        operations: tuple[tuple[str, tuple[GraphRow, ...]], ...] = (
            (_REPOSITORIES, data.repositories),
            (_BRANCHES, data.branches),
            (_ISSUES, data.issues),
            (_PULL_REQUESTS, data.pull_requests),
            (_COMMITS, data.commits),
            (_FILES, data.files),
            (_DEVELOPERS, data.developers),
            (_repository_relationship("Branch", "HAS_BRANCH"), data.repository_branches),
            (_repository_relationship("Issue", "HAS_ISSUE"), data.repository_issues),
            (
                _repository_relationship("PullRequest", "HAS_PULL_REQUEST"),
                data.repository_pull_requests,
            ),
            (_repository_relationship("Commit", "HAS_COMMIT"), data.repository_commits),
            (_repository_relationship("File", "HAS_FILE"), data.repository_files),
            (_key_relationship("Branch", "POINTS_TO", "Commit"), data.branch_heads),
            (
                _key_relationship("PullRequest", "CONTAINS_COMMIT", "Commit"),
                data.pull_request_commits,
            ),
            (
                _key_relationship("PullRequest", "CHANGED", "File"),
                data.pull_request_files,
            ),
            (
                _key_relationship("PullRequest", "RESOLVES", "Issue"),
                data.pull_request_resolutions,
            ),
            (
                _key_relationship("PullRequest", "REFERENCES", "Issue"),
                data.pull_request_references,
            ),
            (_key_relationship("Commit", "PARENT", "Commit"), data.commit_parents),
            (_key_relationship("Commit", "CHANGED", "File"), data.commit_files),
            (_developer_relationship("Issue"), data.developer_issues),
            (_developer_relationship("PullRequest"), data.developer_pull_requests),
            (_developer_relationship("Commit"), data.developer_commits),
        )
        try:
            for query, rows in operations:
                if rows:
                    self._client.execute_query(query, {"rows": list(rows)})
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to persist GitHub development graph.") from exc


_REPOSITORIES = """
UNWIND $rows AS row
MERGE (node:Repository {githubRepositoryId: row.githubRepositoryId})
SET node += row.properties
"""


def _node_query(label: str) -> str:
    return f"""
UNWIND $rows AS row
MERGE (node:{label} {{key: row.key}})
SET node += row.properties
"""


_BRANCHES = _node_query("Branch")
_ISSUES = _node_query("Issue")
_PULL_REQUESTS = _node_query("PullRequest")
_COMMITS = _node_query("Commit")
_FILES = _node_query("File")
_DEVELOPERS = """
UNWIND $rows AS row
MERGE (node:Developer {githubId: row.githubId})
SET node += row.properties
"""


def _repository_relationship(target_label: str, relationship: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (source:Repository {{githubRepositoryId: row.githubRepositoryId}})
MATCH (target:{target_label} {{key: row.toKey}})
MERGE (source)-[relation:{relationship}]->(target)
SET relation += row.properties
"""


def _key_relationship(source_label: str, relationship: str, target_label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (source:{source_label} {{key: row.fromKey}})
MATCH (target:{target_label} {{key: row.toKey}})
MERGE (source)-[relation:{relationship}]->(target)
SET relation += row.properties
"""


def _developer_relationship(target_label: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (source:Developer {{githubId: row.githubId}})
MATCH (target:{target_label} {{key: row.toKey}})
MERGE (source)-[relation:AUTHORED]->(target)
SET relation += row.properties
"""
