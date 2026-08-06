"""Collect the configured GitHub repository and persist its development history."""

from app import create_app
from app.clients.github import GitHubAPIError, GitHubClient
from app.clients.neo4j import Neo4jClient
from app.extensions import db
from app.graph.mappers.github import GitHubGraphMapper
from app.graph.repositories.github_history import (
    GitHubHistoryGraphRepository,
    GraphPersistenceError,
)
from app.repositories.commit_file_change import (
    CommitFileChangeRepository,
    FileChangePersistenceError,
)
from app.services.github_history import GitHubHistoryCollector
from app.services.github_history_import import GitHubHistoryImportService


def main() -> None:
    app = create_app()
    try:
        with app.app_context():
            with (
                GitHubClient.from_config(app.config) as github_client,
                Neo4jClient.from_config(app.config) as neo4j_client,
            ):
                result = GitHubHistoryImportService(
                    collector=GitHubHistoryCollector(github_client),
                    file_change_repository=CommitFileChangeRepository(db.session),
                    graph_mapper=GitHubGraphMapper(),
                    graph_repository=GitHubHistoryGraphRepository(neo4j_client),
                ).import_history()
    except (
        GitHubAPIError,
        FileChangePersistenceError,
        GraphPersistenceError,
        ValueError,
    ) as exc:
        raise SystemExit(f"GitHub history import failed: {exc}") from exc

    print("GitHub history import: OK")
    print(f"repository={result.repository}")
    print(f"branches={result.branches}")
    print(f"issues={result.issues}")
    print(f"pull_requests={result.pull_requests}")
    print(f"commits={result.commits}")
    print(f"file_changes={result.file_changes}")
    print("graph_saved=true")


if __name__ == "__main__":
    main()
