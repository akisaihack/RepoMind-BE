"""Opt-in persistence test against local PostgreSQL and Neo4j containers."""

import os

import pytest

from app import create_app
from app.clients.neo4j import Neo4jClient
from app.dtos.github import (
    BranchDTO,
    CommitDTO,
    CommitFileDTO,
    DevelopmentHistoryDTO,
    RepositoryDTO,
)
from app.extensions import db
from app.graph.mappers.github import GitHubGraphMapper
from app.graph.repositories.github_history import GitHubHistoryGraphRepository
from app.graph.schema import initialize_github_graph_schema
from app.models.commit_file_change import CommitFileChange
from app.repositories.commit_file_change import CommitFileChangeRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to use local databases",
    ),
]

REPOSITORY_ID = 9_999_999_991
AUTHOR_ID = 9_999_999_992


def test_persists_patch_and_graph_relationship() -> None:
    app = create_app()
    history = _history()

    with app.app_context(), Neo4jClient.from_config(app.config) as neo4j_client:
        _cleanup(neo4j_client)
        try:
            file_change_ids = CommitFileChangeRepository(db.session).upsert_changes(
                REPOSITORY_ID,
                history.commits,
            )
            initialize_github_graph_schema(neo4j_client)
            GitHubHistoryGraphRepository(neo4j_client).save(
                GitHubGraphMapper().map(history, file_change_ids)
            )

            records, _, _ = neo4j_client.execute_query(
                """
                MATCH (:Commit {key: $commitKey})-[changed:CHANGED]->(:File {key: $fileKey})
                RETURN changed.fileChangeId AS fileChangeId
                """,
                {
                    "commitKey": f"{REPOSITORY_ID}:commit:integration123",
                    "fileKey": f"{REPOSITORY_ID}:file:app/integration.py",
                },
            )
            change = (
                db.session.query(CommitFileChange)
                .filter_by(github_repository_id=REPOSITORY_ID)
                .one()
            )

            assert records[0]["fileChangeId"] == change.id
            assert change.patch == "@@ -1 +1,2 @@\n-old\n+new\n+line"
            assert change.hunks[0].new_line_count == 2
        finally:
            _cleanup(neo4j_client)


def _cleanup(client: Neo4jClient) -> None:
    db.session.query(CommitFileChange).filter_by(github_repository_id=REPOSITORY_ID).delete()
    db.session.commit()
    client.execute_query(
        """
        MATCH (node)
        WHERE node.githubRepositoryId = $repositoryId
           OR node.githubId = $authorId
           OR node.key STARTS WITH $keyPrefix
        DETACH DELETE node
        """,
        {
            "repositoryId": REPOSITORY_ID,
            "authorId": AUTHOR_ID,
            "keyPrefix": f"{REPOSITORY_ID}:",
        },
    )


def _history() -> DevelopmentHistoryDTO:
    file = CommitFileDTO(
        filename="app/integration.py",
        previous_filename=None,
        status="modified",
        additions=2,
        deletions=1,
        changes=3,
        blob_url=None,
        raw_url=None,
        patch="@@ -1 +1,2 @@\n-old\n+new\n+line",
    )
    return DevelopmentHistoryDTO(
        repository=RepositoryDTO(
            id=REPOSITORY_ID,
            name="integration-test",
            full_name="repomind/integration-test",
            html_url="https://github.com/repomind/integration-test",
            default_branch="main",
            private=False,
            description="Temporary integration fixture",
        ),
        branches=(BranchDTO(name="main", sha="integration123", protected=False),),
        issues=(),
        pull_requests=(),
        commits=(
            CommitDTO(
                sha="integration123",
                message="test: verify persistence",
                html_url="https://github.com/repomind/integration-test/commit/integration123",
                author_name="Integration Test",
                author_id=AUTHOR_ID,
                author_login="integration-test",
                authored_at="2026-08-04T00:00:00Z",
                committed_at="2026-08-04T00:00:00Z",
                parent_shas=(),
                files=(file,),
            ),
        ),
    )
