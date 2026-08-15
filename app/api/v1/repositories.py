"""Repository management API endpoints."""

from dataclasses import asdict
from http import HTTPStatus
from urllib.parse import urlparse
from uuid import UUID

from flask import Blueprint, request

from app.dtos.repositories import (
    RepositoryCreateRequest,
    RepositoryInfo,
)
from app.errors import APIError
from app.extensions import db
from app.models.repository import Repository
from app.repositories.repository import (
    DuplicateRepositoryError,
    RepositoryPersistenceError,
    RepositoryStore,
)
from app.responses import success_response

repositories_bp = Blueprint("repositories", __name__)


from app.repositories.memory_store import get_memory_store, InMemoryRepositoryStore

def _get_repository_store() -> InMemoryRepositoryStore:
    return get_memory_store()


def _normalize_repository_url(value: object) -> str:
    if not isinstance(value, str):
        raise APIError("INVALID_REPOSITORY_URL", "repository_url must be a GitHub URL.")

    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise APIError("INVALID_REPOSITORY_URL", "repository_url must be an HTTPS GitHub URL.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise APIError(
            "INVALID_REPOSITORY_URL",
            "repository_url must identify one owner and repository.",
        )

    owner, repository_name = path_parts
    if repository_name.endswith(".git"):
        repository_name = repository_name.removesuffix(".git")
    if not owner or not repository_name:
        raise APIError(
            "INVALID_REPOSITORY_URL",
            "repository_url must identify one owner and repository.",
        )

    return f"https://github.com/{owner}/{repository_name}"


def _validate_branch(value: object) -> str:
    if not isinstance(value, str):
        raise APIError("INVALID_BRANCH", "branch must be a string.")

    branch = value.strip()
    if not branch:
        raise APIError("INVALID_BRANCH", "branch must not be empty.")
    if len(branch) > 255:
        raise APIError("INVALID_BRANCH", "branch must not exceed 255 characters.")

    return branch


def _parse_repository_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise APIError("INVALID_REPOSITORY_ID", "repository_id must be a UUID.") from exc


def _to_repository_info(repository: dict) -> RepositoryInfo:
    return RepositoryInfo(
        id=str(repository["id"]),
        repository_url=repository["repository_url"],
        branch=repository["branch"],
        analysis_status=repository["analysis_status"],
        latest_analyzed_sha=repository["latest_analyzed_sha"],
    )


@repositories_bp.post("/")
def create_repository():
    """Persist a repository registration in the pending state."""

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("INVALID_REQUEST", "A JSON object is required.")

    create_request = RepositoryCreateRequest(
        repository_url=_normalize_repository_url(data.get("repository_url")),
        branch=_validate_branch(data.get("branch", "main")),
    )

    try:
        repository = _get_repository_store().create(
            repository_url=create_request.repository_url,
            branch=create_request.branch,
        )
    except DuplicateRepositoryError as exc:
        raise APIError(
            "REPOSITORY_ALREADY_EXISTS",
            "This repository and branch are already registered.",
            status=HTTPStatus.CONFLICT,
        ) from exc
    except RepositoryPersistenceError as exc:
        raise APIError(
            "REPOSITORY_PERSISTENCE_FAILED",
            "Repository registration could not be completed.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    return success_response(asdict(_to_repository_info(repository)), status=HTTPStatus.CREATED)


@repositories_bp.get("/<repo_id>")
def get_repository(repo_id: str):
    """Return one registered repository and its analysis state."""

    repository_id = _parse_repository_id(repo_id)
    try:
        repository = _get_repository_store().get(repository_id)
    except RepositoryPersistenceError as exc:
        raise APIError(
            "REPOSITORY_RETRIEVAL_FAILED",
            "Repository details could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    if repository is None:
        raise APIError(
            "REPOSITORY_NOT_FOUND",
            "The requested repository does not exist.",
            status=HTTPStatus.NOT_FOUND,
        )

    return success_response(asdict(_to_repository_info(repository)))


@repositories_bp.get("/")
def list_repositories():
    """Return all registered repositories ordered by most recent update."""

    try:
        repositories = _get_repository_store().list()
    except RepositoryPersistenceError as exc:
        raise APIError(
            "REPOSITORY_RETRIEVAL_FAILED",
            "Repository list could not be loaded.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc

    return success_response(
        {"repositories": [asdict(_to_repository_info(repository)) for repository in repositories]}
    )
