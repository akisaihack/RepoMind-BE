"""Mock data for Repository API."""

import uuid

from app.dtos.repositories import (
    RepositoryInfo,
    RepositoryListResponse,
    RepositoryStatusResponse,
)


def get_mock_repository_creation_status() -> RepositoryStatusResponse:
    """Returns mock status for a newly registered repository."""
    mock_repo_id = f"repo_{uuid.uuid4().hex[:8]}"
    return RepositoryStatusResponse(
        id=mock_repo_id,
        analysis_status="pending",
        latest_analyzed_sha=None,
    )


def get_mock_repository_status(repo_id: str) -> RepositoryStatusResponse:
    """Returns mock completed status for a given repository."""
    return RepositoryStatusResponse(
        id=repo_id,
        analysis_status="pending",
        latest_analyzed_sha=None,
    )


def get_mock_repository_list() -> RepositoryListResponse:
    """Returns a mock list of registered repositories."""
    return RepositoryListResponse(
        repositories=[
            RepositoryInfo(
                id="repo_example1",
                repository_url="https://github.com/callicoder/spring-security-react-ant-design-polls-app",
                branch="main",
                analysis_status="pending",
                latest_analyzed_sha=None,
            )
        ]
    )
