"""Azure OpenAI client construction."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from openai import AzureOpenAI

from app.errors import APIError

AZURE_OPENAI_API_VERSION = "2024-02-01"


def create_azure_openai_client(config: Mapping[str, Any]) -> AzureOpenAI:
    """Create an Azure OpenAI client from application configuration."""
    required_keys = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY")
    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        raise APIError(
            "AZURE_OPENAI_CONFIGURATION_ERROR",
            f"Missing required Azure OpenAI configuration: {', '.join(missing_keys)}.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    return AzureOpenAI(
        azure_endpoint=config["AZURE_OPENAI_ENDPOINT"],
        api_key=config["AZURE_OPENAI_API_KEY"],
        api_version=AZURE_OPENAI_API_VERSION,
    )
