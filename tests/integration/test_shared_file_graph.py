"""Opt-in Neo4j test proving GitHub and code imports share one File node."""

import os

import pytest

from app import create_app
from app.clients.neo4j import Neo4jClient
from app.dtos.graph import GraphDocument, GraphEdge, GraphNode
from app.graph.models import GitHubGraphData
from app.graph.repositories.code_graph import CodeGraphPersistenceError, CodeGraphRepository
from app.graph.repositories.github_history import GitHubHistoryGraphRepository
from app.graph.schema import initialize_graph_schema

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to use local Neo4j",
    ),
]

REPOSITORY_ID = 9_999_999_981
FILE_KEY = f"{REPOSITORY_ID}:file:src/App.java"
COMMIT_KEY = f"{REPOSITORY_ID}:commit:shared-file-test"
CLASS_KEY = f"{REPOSITORY_ID}:class:src/App.java:0"


@pytest.mark.parametrize("code_first", [False, True])
def test_import_order_and_repeated_saves_share_one_file(code_first: bool) -> None:
    app = create_app()
    with Neo4jClient.from_config(app.config) as client:
        _cleanup(client)
        initialize_graph_schema(client)
        github_repository = GitHubHistoryGraphRepository(client)
        code_repository = CodeGraphRepository(client)
        github_data = _github_data()
        code_document = _code_document()

        try:
            if code_first:
                code_repository.save(code_document)
                github_repository.save(github_data)
            else:
                github_repository.save(github_data)
                code_repository.save(code_document)

            github_repository.save(github_data)
            code_repository.save(code_document)

            records, _, _ = client.execute_query(
                """
                MATCH (commit:Commit)-[:CHANGED]->(file:File)-[:DECLARES]->(class)
                WHERE commit.key = $commitKey
                  AND (class:Class OR class:Interface)
                RETURN file.key AS fileKey, class.key AS classKey
                """,
                {"commitKey": COMMIT_KEY},
            )
            counts, _, _ = client.execute_query(
                "MATCH (file:File {key: $fileKey}) RETURN count(file) AS files",
                {"fileKey": FILE_KEY},
            )

            assert [dict(record) for record in records] == [
                {"fileKey": FILE_KEY, "classKey": CLASS_KEY}
            ]
            assert counts[0]["files"] == 1
        finally:
            _cleanup(client)


def test_code_graph_failure_rolls_back_preceding_node_batches() -> None:
    app = create_app()
    rollback_file_key = f"{REPOSITORY_ID}:file:rollback.java"
    invalid_class_key = f"{REPOSITORY_ID}:class:rollback.java:0"
    document = GraphDocument(
        nodes=(
            GraphNode(
                rollback_file_key,
                "File",
                {"path": "rollback.java", "githubRepositoryId": REPOSITORY_ID},
            ),
            GraphNode(
                invalid_class_key,
                "Class",
                {
                    "name": "Rollback",
                    "githubRepositoryId": REPOSITORY_ID,
                    "invalidProperty": {"nested": "maps cannot be node properties"},
                },
            ),
        ),
        edges=(),
    )

    with Neo4jClient.from_config(app.config) as client:
        _cleanup(client)
        initialize_graph_schema(client)
        try:
            with pytest.raises(CodeGraphPersistenceError):
                CodeGraphRepository(client, batch_size=1).save(document)

            records, _, _ = client.execute_query(
                "MATCH (file:File {key: $fileKey}) RETURN count(file) AS files",
                {"fileKey": rollback_file_key},
            )
            assert records[0]["files"] == 0
        finally:
            _cleanup(client)


def _github_data() -> GitHubGraphData:
    return GitHubGraphData(
        repositories=({"githubRepositoryId": REPOSITORY_ID, "properties": {}},),
        commits=(
            {
                "key": COMMIT_KEY,
                "properties": {"githubRepositoryId": REPOSITORY_ID},
            },
        ),
        files=(
            {
                "key": FILE_KEY,
                "properties": {
                    "path": "src/App.java",
                    "githubRepositoryId": REPOSITORY_ID,
                },
            },
        ),
        repository_files=(
            {"githubRepositoryId": REPOSITORY_ID, "toKey": FILE_KEY, "properties": {}},
        ),
        commit_files=({"fromKey": COMMIT_KEY, "toKey": FILE_KEY, "properties": {}},),
    )


def _code_document() -> GraphDocument:
    return GraphDocument(
        nodes=(
            GraphNode(
                FILE_KEY,
                "File",
                {"path": "src/App.java", "githubRepositoryId": REPOSITORY_ID},
            ),
            GraphNode(
                CLASS_KEY,
                "Class",
                {"name": "App", "githubRepositoryId": REPOSITORY_ID},
            ),
        ),
        edges=(GraphEdge("DECLARES", FILE_KEY, CLASS_KEY, {}),),
    )


def _cleanup(client: Neo4jClient) -> None:
    client.execute_query(
        """
        MATCH (node)
        WHERE node.githubRepositoryId = $repositoryId
           OR node.key STARTS WITH $keyPrefix
        DETACH DELETE node
        """,
        {"repositoryId": REPOSITORY_ID, "keyPrefix": f"{REPOSITORY_ID}:"},
    )
