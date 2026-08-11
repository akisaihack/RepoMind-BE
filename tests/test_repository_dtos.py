"""Repository API DTO tests."""

from dataclasses import asdict

from app.dtos.repositories import (
    RepositoryCreateRequest,
    RepositoryInfo,
    RepositoryStatusResponse,
)


def test_serializes_repository_registration_dtos() -> None:
    request = RepositoryCreateRequest(
        repository_url="https://github.com/example/repomind.git",
        branch="develop",
    )
    info = RepositoryInfo(
        id="repository-id",
        repository_url=request.repository_url,
        branch=request.branch,
        analysis_status="pending",
        latest_analyzed_sha=None,
    )
    status = RepositoryStatusResponse(
        id=info.id,
        analysis_status=info.analysis_status,
        latest_analyzed_sha=info.latest_analyzed_sha,
    )

    assert asdict(request) == {
        "repository_url": "https://github.com/example/repomind.git",
        "branch": "develop",
    }
    assert asdict(info)["analysis_status"] == "pending"
    assert asdict(status) == {
        "id": "repository-id",
        "analysis_status": "pending",
        "latest_analyzed_sha": None,
    }
