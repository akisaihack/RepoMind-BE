"""Parse Java sources from a local checkout and persist their Neo4j graph."""

import argparse
from pathlib import Path

from app import create_app
from app.clients.github import GitHubAPIError, GitHubClient
from app.clients.neo4j import Neo4jClient
from app.graph.repositories.code_graph import (
    DEFAULT_BATCH_SIZE,
    CodeGraphPersistenceError,
    CodeGraphRepository,
    CodeGraphValidationError,
)
from app.graph.schema import initialize_graph_schema
from app.services.code_graph_import import CodeGraphImportService
from app.services.repository_identity import RepositoryIdentity, RepositoryIdentityValidator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument("--repository-path", required=True, type=Path)
    parser.add_argument(
        "--commit-hash",
        required=True,
        help="이 코드 스냅샷에 해당하는 실제 Commit SHA.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Rows written per query inside the managed transaction.",
    )
    parser.add_argument(
        "--skip-repository-validation",
        action="store_true",
        help="Import without checking whether origin matches githubRepositoryId.",
    )
    args = parser.parse_args()

    app = create_app()
    try:
        with Neo4jClient.from_config(app.config) as client:
            initialize_graph_schema(client)

            def github_lookup(repository_id: int):
                with GitHubClient.from_config(app.config) as github_client:
                    return github_client.get_repository_by_id(repository_id)

            result = CodeGraphImportService(
                CodeGraphRepository(client, batch_size=args.batch_size),
                RepositoryIdentityValidator(client, github_lookup),
                _print_repository_identity,
            ).import_repository(
                args.github_repository_id,
                args.repository_path,
                args.commit_hash,
                skip_repository_validation=args.skip_repository_validation,
            )
    except (
        CodeGraphPersistenceError,
        CodeGraphValidationError,
        GitHubAPIError,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(f"Code graph import failed: {exc}") from exc

    print("Code graph import: OK")
    for field in result.__dataclass_fields__:
        print(f"{field}={getattr(result, field)}")


def _print_repository_identity(identity: RepositoryIdentity) -> None:
    if identity.skipped:
        print("repository_validation=skipped")
        return
    print("repository_validation=matched")
    print(f"repository={identity.expected_full_name}")
    print(f"repository_validation_source={identity.source}")


if __name__ == "__main__":
    main()
