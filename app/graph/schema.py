"""Idempotent Neo4j constraints required by the GitHub history graph."""

from app.clients.neo4j import Neo4jClient

CONSTRAINTS = (
    "CREATE CONSTRAINT repository_github_id IF NOT EXISTS "
    "FOR (n:Repository) REQUIRE n.githubRepositoryId IS UNIQUE",
    "CREATE CONSTRAINT branch_key IF NOT EXISTS FOR (n:Branch) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT issue_key IF NOT EXISTS FOR (n:Issue) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT pull_request_key IF NOT EXISTS FOR (n:PullRequest) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT commit_key IF NOT EXISTS FOR (n:Commit) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT file_key IF NOT EXISTS FOR (n:File) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT package_key IF NOT EXISTS FOR (n:Package) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT class_key IF NOT EXISTS FOR (n:Class) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT interface_key IF NOT EXISTS FOR (n:Interface) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT method_key IF NOT EXISTS FOR (n:Method) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT endpoint_key IF NOT EXISTS FOR (n:Endpoint) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT developer_github_id IF NOT EXISTS "
    "FOR (n:Developer) REQUIRE n.githubId IS UNIQUE",
)


def initialize_github_graph_schema(client: Neo4jClient) -> None:
    """Create every graph constraint safely on repeated execution."""
    for query in CONSTRAINTS:
        client.execute_query(query)


def initialize_graph_schema(client: Neo4jClient) -> None:
    """Create constraints for both GitHub history and source-code graphs."""
    initialize_github_graph_schema(client)
