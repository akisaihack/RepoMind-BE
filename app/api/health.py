"""Health-check endpoint."""

from flask import Blueprint

from app.responses import success_response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    """Report whether the HTTP application is available."""
    return success_response({"status": "healthy"})
