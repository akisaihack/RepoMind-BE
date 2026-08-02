"""Azure OpenAI embedding service."""

from http import HTTPStatus
from typing import overload

from openai import AzureOpenAI, OpenAIError

from app.errors import APIError


class EmbeddingService:
    """Generate embeddings through an Azure OpenAI deployment."""

    def __init__(self, client: AzureOpenAI, deployment: str) -> None:
        if not deployment.strip():
            raise APIError(
                "AZURE_OPENAI_CONFIGURATION_ERROR",
                "Azure OpenAI embedding deployment is not configured.",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        self._client = client
        self._deployment = deployment

    @overload
    def embed(self, value: str) -> list[float]: ...

    @overload
    def embed(self, value: list[str]) -> list[list[float]]: ...

    def embed(self, value: str | list[str]) -> list[float] | list[list[float]]:
        """Embed one string or a non-empty list of non-empty strings."""
        inputs, is_single = self._validate_input(value)

        try:
            response = self._client.embeddings.create(
                model=self._deployment,
                input=inputs,
            )
        except OpenAIError as exc:
            raise APIError(
                "EMBEDDING_PROVIDER_ERROR",
                "The embedding provider request failed.",
                status=HTTPStatus.BAD_GATEWAY,
            ) from exc

        embeddings = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        return embeddings[0] if is_single else embeddings

    @staticmethod
    def _validate_input(value: str | list[str]) -> tuple[list[str], bool]:
        if isinstance(value, str):
            if not value.strip():
                raise APIError(
                    "INVALID_EMBEDDING_INPUT",
                    "Embedding text must not be empty.",
                )
            return [value], True

        if not isinstance(value, list) or not value:
            raise APIError(
                "INVALID_EMBEDDING_INPUT",
                "Embedding text list must not be empty.",
            )
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise APIError(
                "INVALID_EMBEDDING_INPUT",
                "Embedding text list must contain only non-empty strings.",
            )
        return value, False
