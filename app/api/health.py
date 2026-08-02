"""Application and database health-check endpoints."""

from http import HTTPStatus

from flask import Blueprint
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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
