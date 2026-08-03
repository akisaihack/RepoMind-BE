"""Embedding test endpoint."""

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from app.clients.azure_openai import create_azure_openai_client
from app.errors import APIError
from app.services.embedding import EmbeddingService

embeddings_bp = Blueprint("embeddings", __name__, url_prefix="/embeddings")
EMBEDDING_PREVIEW_SIZE = 3


def get_embedding_service() -> EmbeddingService:
    """Build an embedding service from the current application config."""
    deployment = current_app.config.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    if not deployment:
        raise APIError(
            "AZURE_OPENAI_CONFIGURATION_ERROR",
            "Azure OpenAI embedding deployment is not configured.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    client = create_azure_openai_client(current_app.config)
    return EmbeddingService(client, deployment)


@embeddings_bp.post("/test")
def test_embedding():
    """Generate an embedding and expose only its dimension and a short preview."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "text" not in payload:
        raise APIError(
            "INVALID_REQUEST",
            "Request body must contain a 'text' field.",
        )

    embedding = get_embedding_service().embed(payload["text"])
    return jsonify(
        {
            "dimension": len(embedding),
            "embeddingPreview": embedding[:EMBEDDING_PREVIEW_SIZE],
        }
    )
