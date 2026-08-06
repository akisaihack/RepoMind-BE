"""Mock data for Repository API."""

import uuid
from app.dtos.repositories import (
    RepositoryStatusResponse,
    RepositoryInfo,
    RepositoryListResponse,
)


def get_mock_repository_creation_status() -> RepositoryStatusResponse:
    """Returns mock status for a newly registered repository."""
    mock_repo_id = f"repo_{uuid.uuid4().hex[:8]}"
    return RepositoryStatusResponse(
        repo_id=mock_repo_id,
        status="indexing",
        progress_percent=15,
        file_count=0
    )


def get_mock_repository_status(repo_id: str) -> RepositoryStatusResponse:
    """Returns mock completed status for a given repository."""
    return RepositoryStatusResponse(
        repo_id=repo_id,
        status="completed",
        progress_percent=100,
        file_count=142
    )


def get_mock_repository_list() -> RepositoryListResponse:
    """Returns a mock list of registered repositories."""
    return RepositoryListResponse(
        repositories=[
            RepositoryInfo(
                repo_id="repo_example1",
                name="spring-security-react-ant-design-polls-app",
                repo_url="https://github.com/callicoder/spring-security-react-ant-design-polls-app",
                status="completed"
            )
        ]
    )
