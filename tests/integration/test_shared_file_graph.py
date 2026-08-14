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
                _save_code(code_repository, code_document, "initial")
                github_repository.save(github_data)
            else:
                github_repository.save(github_data)
                _save_code(code_repository, code_document, "initial")

            github_repository.save(github_data)
            _save_code(code_repository, code_document, "repeated")

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
            code_repository = CodeGraphRepository(client, batch_size=1)
            _save_code(code_repository, _code_document(), "last-successful-run")
            with pytest.raises(CodeGraphPersistenceError):
                code_repository.save(
                    document,
                    github_repository_id=REPOSITORY_ID,
                    analysis_run_id="failed-run",
                )

            records, _, _ = client.execute_query(
                """
                RETURN
                    count { (:File {key: $rollbackFileKey}) } AS rolledBackFiles,
                    count { (:Class {key: $preservedClassKey}) } AS preservedClasses
                """,
                {
                    "rollbackFileKey": rollback_file_key,
                    "preservedClassKey": CLASS_KEY,
                },
            )
            assert dict(records[0]) == {"rolledBackFiles": 0, "preservedClasses": 1}
        finally:
            _cleanup(client)


def test_reanalysis_removes_stale_code_but_preserves_github_file_history() -> None:
    app = create_app()
    old_method_key = f"{CLASS_KEY}:method:0"
    renamed_file_key = f"{REPOSITORY_ID}:file:src/RenamedApp.java"
    renamed_class_key = f"{REPOSITORY_ID}:class:src/RenamedApp.java:0"
    initial_document = GraphDocument(
        nodes=(
            *_code_document().nodes,
            GraphNode(
                old_method_key, "Method", {"name": "removed", "githubRepositoryId": REPOSITORY_ID}
            ),
        ),
        edges=(*_code_document().edges, GraphEdge("CONTAINS", CLASS_KEY, old_method_key, {})),
    )
    current_document = GraphDocument(
        nodes=(
            GraphNode(
                renamed_file_key,
                "File",
                {"path": "src/RenamedApp.java", "githubRepositoryId": REPOSITORY_ID},
            ),
            GraphNode(
                renamed_class_key,
                "Class",
                {"name": "RenamedApp", "githubRepositoryId": REPOSITORY_ID},
            ),
        ),
        edges=(GraphEdge("DECLARES", renamed_file_key, renamed_class_key, {}),),
    )

    with Neo4jClient.from_config(app.config) as client:
        _cleanup(client)
        initialize_graph_schema(client)
        try:
            github_repository = GitHubHistoryGraphRepository(client)
            code_repository = CodeGraphRepository(client)
            github_repository.save(_github_data())
            _save_code(code_repository, initial_document, "before-rename")
            _save_code(code_repository, current_document, "after-rename")

            records, _, _ = client.execute_query(
                """
                MATCH (commit:Commit {key: $commitKey})-[:CHANGED]->(file:File {key: $fileKey})
                RETURN
                    count(file) AS githubFiles,
                    count { (file)-[:DECLARES]->() } AS declarations,
                    count { (:Method {key: $methodKey}) } AS staleMethods,
                    count { (:Class {key: $classKey}) } AS currentClasses
                """,
                {
                    "commitKey": COMMIT_KEY,
                    "fileKey": FILE_KEY,
                    "methodKey": old_method_key,
                    "classKey": renamed_class_key,
                },
            )

            assert dict(records[0]) == {
                "githubFiles": 1,
                "declarations": 0,
                "staleMethods": 0,
                "currentClasses": 1,
            }
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


def _save_code(
    repository: CodeGraphRepository,
    document: GraphDocument,
    analysis_run_id: str,
) -> None:
    repository.save(
        document,
        github_repository_id=REPOSITORY_ID,
        analysis_run_id=analysis_run_id,
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
