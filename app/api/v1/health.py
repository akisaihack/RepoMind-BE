"""Application and database health-check endpoints."""

from http import HTTPStatus

from flask import Blueprint, current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.clients.neo4j import Neo4jClient
from app.errors import APIError
from app.extensions import db
from app.responses import success_response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    """Report whether the HTTP application is available."""
    return success_response({"status": "healthy"})


@health_bp.get("/health/db")
def database_health_check():
    """Verify that the application can execute a query against its database."""
    try:
        db.session.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as exc:
        raise APIError(
            "DATABASE_UNAVAILABLE",
            "The database connection is unavailable.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    return success_response(
        {
            "status": "healthy",
            "database": "connected",
        }
    )


@health_bp.get("/health/readiness")
def rag_readiness_check():
    """Verify the configuration and services required by RAG chat requests."""
    _validate_rag_configuration()
    _verify_postgres_and_pgvector()
    _verify_neo4j()

    return success_response(
        {
            "status": "ready",
            "database": "connected",
            "pgvector": "available",
            "neo4j": "connected",
            "azure_openai": "configured",
        }
    )


def _validate_rag_configuration() -> None:
    required_keys = (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "AZURE_OPENAI_DEPLOYMENT",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
    )
    missing_keys = [key for key in required_keys if not current_app.config.get(key)]
    if missing_keys:
        raise APIError(
            "RAG_CONFIGURATION_INCOMPLETE",
            "Required RAG configuration is missing.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            details={"missing": missing_keys},
        )


def _verify_postgres_and_pgvector() -> None:
    try:
        db.session.execute(text("SELECT 1")).scalar_one()
        has_pgvector = db.session.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()
    except SQLAlchemyError as exc:
        raise APIError(
            "DATABASE_UNAVAILABLE",
            "The database connection is unavailable.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    if not has_pgvector:
        raise APIError(
            "PGVECTOR_UNAVAILABLE",
            "The PostgreSQL vector extension is unavailable.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )


def _verify_neo4j() -> None:
    try:
        with Neo4jClient.from_config(current_app.config) as client:
            client.verify_connectivity()
    except Exception as exc:
        raise APIError(
            "NEO4J_UNAVAILABLE",
            "The Neo4j connection is unavailable.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc
