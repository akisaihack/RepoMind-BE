"""Neo4j driver lifecycle and connectivity client."""

from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any, Self, TypeVar

from neo4j import GraphDatabase, ManagedTransaction

TransactionResult = TypeVar("TransactionResult")


class Neo4jClient:
    """Own a Neo4j driver without exposing credentials to callers or logs."""

    def __init__(self, uri: str, username: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> Self:
        """Create a client from Flask application configuration."""
        required_keys = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")
        missing_keys = [key for key in required_keys if not config.get(key)]
        if missing_keys:
            raise ValueError(f"Missing required Neo4j configuration: {', '.join(missing_keys)}.")

        return cls(
            uri=config["NEO4J_URI"],
            username=config["NEO4J_USERNAME"],
            password=config["NEO4J_PASSWORD"],
        )

    def verify_connectivity(self) -> None:
        """Raise a Neo4j driver exception when the server cannot be reached."""
        self._driver.verify_connectivity()

    def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a parameterized query without exposing the underlying driver."""
        return self._driver.execute_query(query, parameters_=parameters or {})

    def execute_write(
        self,
        work: Callable[[ManagedTransaction], TransactionResult],
    ) -> TransactionResult:
        """Run a unit of work in one managed write transaction."""
        with self._driver.session() as session:
            return session.execute_write(work)

    def close(self) -> None:
        """Release all connections owned by the driver."""
        self._driver.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
