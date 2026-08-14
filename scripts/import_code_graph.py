"""Parse Java sources from a local checkout and persist their Neo4j graph."""

import argparse
from pathlib import Path

from app import create_app
from app.clients.neo4j import Neo4jClient
from app.graph.repositories.code_graph import (
    CodeGraphPersistenceError,
    CodeGraphRepository,
    CodeGraphValidationError,
)
from app.graph.schema import initialize_graph_schema
from app.services.code_graph_import import CodeGraphImportService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument("--repository-path", required=True, type=Path)
    args = parser.parse_args()

    app = create_app()
    try:
        with Neo4jClient.from_config(app.config) as client:
            initialize_graph_schema(client)
            result = CodeGraphImportService(CodeGraphRepository(client)).import_repository(
                args.github_repository_id, args.repository_path
            )
    except (
        CodeGraphPersistenceError,
        CodeGraphValidationError,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(f"Code graph import failed: {exc}") from exc

    print("Code graph import: OK")
    for field in result.__dataclass_fields__:
        print(f"{field}={getattr(result, field)}")


if __name__ == "__main__":
    main()
