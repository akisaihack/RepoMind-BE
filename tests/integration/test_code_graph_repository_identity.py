"""Opt-in repository identity validation test against local Neo4j."""

import os
import subprocess
from unittest.mock import Mock

import pytest

from app import create_app
from app.clients.neo4j import Neo4jClient
from app.graph.repositories.code_graph import CodeGraphRepository
from app.services.code_graph_import import CodeGraphImportService
from app.services.repository_identity import RepositoryIdentityValidator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to use local Neo4j",
    ),
]

REPOSITORY_ID = 9_999_999_971
FULL_NAME = "repomind/repository-identity-test"


def test_matching_local_origin_and_neo4j_repository_can_import(tmp_path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            f"git@github.com:{FULL_NAME}.git",
        ],
        check=True,
        capture_output=True,
    )
    app = create_app()
    github_lookup = Mock(side_effect=AssertionError("Neo4j identity should be preferred"))

    with Neo4jClient.from_config(app.config) as client:
        _cleanup(client)
        try:
            client.execute_query(
                """
                CREATE (:Repository {
                    githubRepositoryId: $repositoryId,
                    fullName: $fullName
                })
                """,
                {"repositoryId": REPOSITORY_ID, "fullName": FULL_NAME},
            )
            result = CodeGraphImportService(
                CodeGraphRepository(client),
                RepositoryIdentityValidator(client, github_lookup),
            ).import_repository(REPOSITORY_ID, tmp_path, "identity-test")

            assert result.repository_full_name == FULL_NAME
            assert result.repository_validation_source == "neo4j"
            github_lookup.assert_not_called()
        finally:
            _cleanup(client)


def _cleanup(client: Neo4jClient) -> None:
    client.execute_query(
        "MATCH (node {githubRepositoryId: $repositoryId}) DETACH DELETE node",
        {"repositoryId": REPOSITORY_ID},
    )
