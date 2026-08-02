"""Embedding test API tests."""

from unittest.mock import Mock, patch

from flask.testing import FlaskClient


def test_embedding_api_returns_dimension_and_preview(client: FlaskClient) -> None:
    service = Mock()
    service.embed.return_value = [0.01, -0.02, 0.03, 0.04]

    with patch("app.api.embeddings.get_embedding_service", return_value=service):
        response = client.post(
            "/api/v1/embeddings/test",
            json={"text": "예약 취소 처리 흐름을 분석합니다."},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "dimension": 4,
        "embeddingPreview": [0.01, -0.02, 0.03],
    }
    service.embed.assert_called_once_with("예약 취소 처리 흐름을 분석합니다.")
