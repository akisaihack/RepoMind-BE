"""Create idempotent constraints for the GitHub development graph."""

from app import create_app
from app.clients.neo4j import Neo4jClient
from app.graph.schema import initialize_graph_schema


def main() -> None:
    app = create_app()
    with Neo4jClient.from_config(app.config) as client:
        initialize_graph_schema(client)
    print("Neo4j graph schema: OK")


if __name__ == "__main__":
    main()
