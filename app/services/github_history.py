"""Collect and normalize GitHub repository development history."""

import logging
from typing import Any

from app.clients.github import GitHubClient
from app.dtos.github import (
    BranchDTO,
    CommitDTO,
    CommitFileDTO,
    DevelopmentHistoryDTO,
    IssueDTO,
    PullRequestDTO,
    RepositoryDTO,
)
from app.services.github_references import extract_issue_references

logger = logging.getLogger(__name__)


class GitHubHistoryCollector:
    """Collect repository, branch, issue, pull request, and commit history."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    def collect(self, branch: str) -> DevelopmentHistoryDTO:
        """Collect resources and commits reachable from the requested branch."""
        logger.info("GitHub 데이터 수집을 시작합니다. 브랜치=%s", branch)
        repository = _to_repository(self._client.get_repository())
        logger.info("GitHub 저장소 정보를 조회했습니다. 저장소=%s", repository.full_name)
        branches = tuple(_to_branch(item) for item in self._client.list_branches())
        logger.info("GitHub 브랜치 목록을 조회했습니다. 브랜치=%s개", len(branches))

        issue_summaries = self._client.list_issues()
        logger.info("GitHub 이슈 상세 조회를 시작합니다. 전체=%s개", len(issue_summaries))
        issues = []
        for index, item in enumerate(issue_summaries, start=1):
            issues.append(_to_issue(self._client.get_issue(item["number"])))
            _log_progress("issues", index, len(issue_summaries))

        pull_request_summaries = self._client.list_pull_requests()
        logger.info("GitHub PR 상세 조회를 시작합니다. 전체=%s개", len(pull_request_summaries))
        pull_requests = []
        for index, item in enumerate(pull_request_summaries, start=1):
            pull_requests.append(self._collect_pull_request(item["number"]))
            _log_progress("pull_requests", index, len(pull_request_summaries))

        commit_summaries = self._client.list_commits(branch)
        logger.info(
            "GitHub 커밋 상세 조회를 시작합니다. 브랜치=%s, 전체=%s개",
            branch,
            len(commit_summaries),
        )
        commits = []
        for index, item in enumerate(commit_summaries, start=1):
            commits.append(_to_commit(self._client.get_commit(item["sha"])))
            _log_progress("commits", index, len(commit_summaries))

        logger.info(
            "GitHub 데이터 수집을 완료했습니다. 브랜치=%s개, 이슈=%s개, PR=%s개, "
            "커밋=%s개",
            len(branches),
            len(issues),
            len(pull_requests),
            len(commits),
        )

        return DevelopmentHistoryDTO(
            repository=repository,
            branches=branches,
            issues=tuple(issues),
            pull_requests=tuple(pull_requests),
            commits=tuple(commits),
        )

    def _collect_pull_request(self, number: int) -> PullRequestDTO:
        pull_request = self._client.get_pull_request(number)
        commits = self._client.list_pull_request_commits(number)
        files = self._client.list_pull_request_files(number)
        return _to_pull_request(pull_request, commits, files)


def _log_progress(resource: str, current: int, total: int) -> None:
    if current == 1 or current == total or current % 10 == 0:
        labels = {"issues": "이슈", "pull_requests": "PR", "commits": "커밋"}
        logger.info("GitHub %s 조회 진행률=%s/%s", labels[resource], current, total)


def _to_repository(data: dict[str, Any]) -> RepositoryDTO:
    return RepositoryDTO(
        id=data["id"],
        name=data["name"],
        full_name=data["full_name"],
        html_url=data["html_url"],
        default_branch=data["default_branch"],
        private=data["private"],
        description=data.get("description"),
    )


def _to_branch(data: dict[str, Any]) -> BranchDTO:
    return BranchDTO(
        name=data["name"],
        sha=data["commit"]["sha"],
        protected=data.get("protected", False),
    )


def _to_issue(data: dict[str, Any]) -> IssueDTO:
    return IssueDTO(
        number=data["number"],
        title=data["title"],
        state=data["state"],
        body=data.get("body"),
        author_id=_user_id(data.get("user")),
        author=_login(data.get("user")),
        html_url=data["html_url"],
        labels=tuple(label["name"] for label in data.get("labels", [])),
        assignees=tuple(assignee["login"] for assignee in data.get("assignees", [])),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        closed_at=data.get("closed_at"),
    )


def _to_file(data: dict[str, Any]) -> CommitFileDTO:
    return CommitFileDTO(
        filename=data["filename"],
        previous_filename=data.get("previous_filename"),
        status=data["status"],
        additions=data.get("additions", 0),
        deletions=data.get("deletions", 0),
        changes=data.get("changes", 0),
        blob_url=data.get("blob_url"),
        raw_url=data.get("raw_url"),
        patch=data.get("patch"),
    )


def _to_commit(data: dict[str, Any]) -> CommitDTO:
    commit = data["commit"]
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    return CommitDTO(
        sha=data["sha"],
        message=commit["message"],
        html_url=data["html_url"],
        author_name=author.get("name"),
        author_id=_user_id(data.get("author")),
        author_login=_login(data.get("author")),
        authored_at=author.get("date"),
        committed_at=committer.get("date"),
        parent_shas=tuple(parent["sha"] for parent in data.get("parents", [])),
        files=tuple(_to_file(file) for file in data.get("files", [])),
    )


def _to_pull_request(
    data: dict[str, Any],
    commits: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> PullRequestDTO:
    return PullRequestDTO(
        number=data["number"],
        title=data["title"],
        state=data["state"],
        body=data.get("body"),
        author_id=_user_id(data.get("user")),
        author=_login(data.get("user")),
        html_url=data["html_url"],
        base_branch=data["base"]["ref"],
        head_branch=data["head"]["ref"],
        head_sha=data["head"]["sha"],
        merge_commit_sha=data.get("merge_commit_sha"),
        merged=data.get("merged", False),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        closed_at=data.get("closed_at"),
        merged_at=data.get("merged_at"),
        commit_shas=tuple(commit["sha"] for commit in commits),
        files=tuple(_to_file(file) for file in files),
        issue_references=extract_issue_references(data.get("title"), data.get("body")),
    )


def _login(user: dict[str, Any] | None) -> str | None:
    return user.get("login") if user else None


def _user_id(user: dict[str, Any] | None) -> int | None:
    return user.get("id") if user else None
