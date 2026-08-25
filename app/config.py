"""Environment-based application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class BaseConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///repomind.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    NEO4J_HTTP_PORT = int(os.getenv("NEO4J_HTTP_PORT", "7474"))
    NEO4J_BOLT_PORT = int(os.getenv("NEO4J_BOLT_PORT", "7687"))
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_REPOSITORY_OWNER = os.getenv("GITHUB_REPOSITORY_OWNER")
    GITHUB_REPOSITORY_NAME = os.getenv("GITHUB_REPOSITORY_NAME")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    AZURE_OPENAI_NANO_DEPLOYMENT = os.getenv("AZURE_OPENAI_NANO_DEPLOYMENT")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str | None = None) -> type[BaseConfig]:
    """Return the configuration class for the requested environment."""
    environment = config_name or os.getenv("APP_ENV", "development")
    try:
        return CONFIGS[environment]
    except KeyError as exc:
        supported = ", ".join(CONFIGS)
        raise ValueError(f"Unknown APP_ENV '{environment}'. Choose one of: {supported}") from exc
