"""API blueprint registration."""

from flask import Blueprint

from app.api.v1.embeddings import embeddings_bp
from app.api.v1.health import health_bp
from app.api.v1.chat import chat_bp
from app.api.v1.repositories import repositories_bp
from app.api.v1.sessions import sessions_bp

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(health_bp)
api_v1.register_blueprint(embeddings_bp)
api_v1.register_blueprint(chat_bp)
api_v1.register_blueprint(repositories_bp, url_prefix="/repositories")
api_v1.register_blueprint(sessions_bp, url_prefix="/sessions")
