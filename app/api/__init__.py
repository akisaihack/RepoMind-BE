"""API blueprint registration."""

from flask import Blueprint

from app.api.embeddings import embeddings_bp
from app.api.health import health_bp

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(health_bp)
api_v1.register_blueprint(embeddings_bp)
