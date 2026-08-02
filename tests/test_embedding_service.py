"""Embedding service tests."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai import OpenAIError

from app.errors import APIError
from app.services.embedding import EmbeddingService


def embedding_response(*embeddings: list[float]) -> SimpleNamespace:
    data = [
        SimpleNamespace(index=index, embedding=embedding)
        for index, embedding in enumerate(embeddings)
    ]
    return SimpleNamespace(data=data)


def test_embed_single_string() -> None:
    client = Mock()
    client.embeddings.create.return_value = embedding_response([0.1, -0.2, 0.3])
    service = EmbeddingService(client, "shared-embedding")

    result = service.embed("예약 취소 처리 흐름을 분석합니다.")

    assert result == [0.1, -0.2, 0.3]
    client.embeddings.create.assert_called_once_with(
        model="shared-embedding",
        input=["예약 취소 처리 흐름을 분석합니다."],
    )


def test_embed_string_list() -> None:
    client = Mock()
    client.embeddings.create.return_value = embedding_response([0.1], [0.2])
    service = EmbeddingService(client, "shared-embedding")

    result = service.embed(["첫 번째", "두 번째"])

    assert result == [[0.1], [0.2]]


@pytest.mark.parametrize("value", ["", "   "])
def test_embed_rejects_empty_string(value: str) -> None:
    service = EmbeddingService(Mock(), "shared-embedding")

    with pytest.raises(APIError) as exc_info:
        service.embed(value)

    assert exc_info.value.code == "INVALID_EMBEDDING_INPUT"


def test_embed_rejects_empty_list() -> None:
    client = Mock()
    service = EmbeddingService(client, "shared-embedding")

    with pytest.raises(APIError) as exc_info:
        service.embed([])

    assert exc_info.value.code == "INVALID_EMBEDDING_INPUT"
    client.embeddings.create.assert_not_called()


def test_embed_converts_external_api_error() -> None:
    client = Mock()
    client.embeddings.create.side_effect = OpenAIError("provider failure")
    service = EmbeddingService(client, "shared-embedding")

    with pytest.raises(APIError) as exc_info:
        service.embed("테스트")

    assert exc_info.value.code == "EMBEDDING_PROVIDER_ERROR"
    assert exc_info.value.status == 502
    assert str(exc_info.value) == "The embedding provider request failed."
