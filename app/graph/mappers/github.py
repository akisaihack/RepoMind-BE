"""Map normalized GitHub history into Neo4j node and relationship batches."""

from typing import Any

from app.dtos.github import DevelopmentHistoryDTO
from app.graph.identifiers import (
    file_key as make_file_key,
)
from app.graph.identifiers import (
    normalize_repository_path,
    repository_scoped_key,
)
from app.graph.models import GitHubGraphData, GraphRow


class GitHubGraphMapper:
    def map(
        self,
        history: DevelopmentHistoryDTO,
        file_change_ids: dict[tuple[str, str], int],
    ) -> GitHubGraphData:
        repository_id = history.repository.id
        repository = {
            "githubRepositoryId": repository_id,
            "properties": _properties(
                name=history.repository.name,
                fullName=history.repository.full_name,
                url=history.repository.html_url,
                defaultBranch=history.repository.default_branch,
                private=history.repository.private,
                description=history.repository.description,
            ),
        }

        branches: dict[str, GraphRow] = {}
        issues: dict[str, GraphRow] = {}
        pull_requests: dict[str, GraphRow] = {}
        commits: dict[str, GraphRow] = {}
        files: dict[str, GraphRow] = {}
        developers: dict[int, GraphRow] = {}

        repository_branches: list[GraphRow] = []
        repository_issues: list[GraphRow] = []
        repository_pull_requests: list[GraphRow] = []
        repository_commits: list[GraphRow] = []
        repository_files: dict[str, GraphRow] = {}
        branch_heads: list[GraphRow] = []
        pull_request_commits: list[GraphRow] = []
        pull_request_files: list[GraphRow] = []
        pull_request_resolutions: list[GraphRow] = []
        pull_request_references: list[GraphRow] = []
        commit_parents: list[GraphRow] = []
        commit_files: list[GraphRow] = []
        developer_issues: list[GraphRow] = []
        developer_pull_requests: list[GraphRow] = []
        developer_commits: list[GraphRow] = []

        def ensure_commit(sha: str) -> str:
            key = repository_scoped_key(repository_id, "commit", sha)
            commits.setdefault(key, {"key": key, "properties": {"sha": sha}})
            return key

        def ensure_file(path: str) -> str:
            normalized_path = normalize_repository_path(path)
            key = make_file_key(repository_id, normalized_path)
            files.setdefault(
                key,
                {
                    "key": key,
                    "properties": {
                        "path": normalized_path,
                        "githubRepositoryId": repository_id,
                    },
                },
            )
            repository_files.setdefault(key, _repository_relation(repository_id, key))
            return key

        def ensure_developer(github_id: int | None, login: str | None) -> None:
            if github_id is None:
                return
            developers[github_id] = {
                "githubId": github_id,
                "properties": _properties(login=login),
            }

        for branch in history.branches:
            key = repository_scoped_key(repository_id, "branch", branch.name)
            branches[key] = {
                "key": key,
                "properties": _properties(
                    name=branch.name,
                    protected=branch.protected,
                    githubRepositoryId=repository_id,
                ),
            }
            commit_key = ensure_commit(branch.sha)
            repository_branches.append(_repository_relation(repository_id, key))
            branch_heads.append({"fromKey": key, "toKey": commit_key, "properties": {}})

        for issue in history.issues:
            key = repository_scoped_key(repository_id, "issue", issue.number)
            issues[key] = {
                "key": key,
                "properties": _properties(
                    number=issue.number,
                    title=issue.title,
                    body=issue.body,
                    state=issue.state,
                    url=issue.html_url,
                    labels=list(issue.labels),
                    assignees=list(issue.assignees),
                    createdAt=issue.created_at,
                    updatedAt=issue.updated_at,
                    closedAt=issue.closed_at,
                    githubRepositoryId=repository_id,
                ),
            }
            repository_issues.append(_repository_relation(repository_id, key))
            ensure_developer(issue.author_id, issue.author)
            if issue.author_id is not None:
                developer_issues.append(
                    {"githubId": issue.author_id, "toKey": key, "properties": {}}
                )

        for pull_request in history.pull_requests:
            key = repository_scoped_key(repository_id, "pr", pull_request.number)
            pull_requests[key] = {
                "key": key,
                "properties": _properties(
                    number=pull_request.number,
                    title=pull_request.title,
                    body=pull_request.body,
                    state=pull_request.state,
                    url=pull_request.html_url,
                    baseBranch=pull_request.base_branch,
                    headBranch=pull_request.head_branch,
                    headSha=pull_request.head_sha,
                    mergeCommitSha=pull_request.merge_commit_sha,
                    merged=pull_request.merged,
                    createdAt=pull_request.created_at,
                    updatedAt=pull_request.updated_at,
                    closedAt=pull_request.closed_at,
                    mergedAt=pull_request.merged_at,
                    githubRepositoryId=repository_id,
                ),
            }
            repository_pull_requests.append(_repository_relation(repository_id, key))
            ensure_developer(pull_request.author_id, pull_request.author)
            if pull_request.author_id is not None:
                developer_pull_requests.append(
                    {"githubId": pull_request.author_id, "toKey": key, "properties": {}}
                )

            for sha in pull_request.commit_shas:
                pull_request_commits.append(
                    {"fromKey": key, "toKey": ensure_commit(sha), "properties": {}}
                )
            ensure_commit(pull_request.head_sha)
            if pull_request.merge_commit_sha:
                ensure_commit(pull_request.merge_commit_sha)

            for file in pull_request.files:
                file_key = ensure_file(file.filename)
                pull_request_files.append(
                    {
                        "fromKey": key,
                        "toKey": file_key,
                        "properties": _change_properties(file),
                    }
                )

            for reference in pull_request.issue_references:
                relation = {
                    "fromKey": key,
                    "toKey": repository_scoped_key(repository_id, "issue", reference.issue_number),
                    "properties": {},
                }
                if reference.reference_type == "resolves":
                    pull_request_resolutions.append(relation)
                else:
                    pull_request_references.append(relation)

        for commit in history.commits:
            key = ensure_commit(commit.sha)
            commits[key]["properties"] = _properties(
                sha=commit.sha,
                message=commit.message,
                url=commit.html_url,
                authorName=commit.author_name,
                authoredAt=commit.authored_at,
                committedAt=commit.committed_at,
                githubRepositoryId=repository_id,
            )
            ensure_developer(commit.author_id, commit.author_login)
            if commit.author_id is not None:
                developer_commits.append(
                    {"githubId": commit.author_id, "toKey": key, "properties": {}}
                )
            for parent_sha in commit.parent_shas:
                commit_parents.append(
                    {"fromKey": key, "toKey": ensure_commit(parent_sha), "properties": {}}
                )
            for file in commit.files:
                file_key = ensure_file(file.filename)
                properties = _change_properties(file)
                file_change_id = file_change_ids.get((commit.sha, file.filename))
                if file_change_id is not None:
                    properties["fileChangeId"] = file_change_id
                commit_files.append({"fromKey": key, "toKey": file_key, "properties": properties})

        for commit_key in commits:
            repository_commits.append(_repository_relation(repository_id, commit_key))

        return GitHubGraphData(
            repositories=(repository,),
            branches=tuple(branches.values()),
            issues=tuple(issues.values()),
            pull_requests=tuple(pull_requests.values()),
            commits=tuple(commits.values()),
            files=tuple(files.values()),
            developers=tuple(developers.values()),
            repository_branches=tuple(repository_branches),
            repository_issues=tuple(repository_issues),
            repository_pull_requests=tuple(repository_pull_requests),
            repository_commits=tuple(repository_commits),
            repository_files=tuple(repository_files.values()),
            branch_heads=tuple(branch_heads),
            pull_request_commits=tuple(pull_request_commits),
            pull_request_files=tuple(pull_request_files),
            pull_request_resolutions=tuple(pull_request_resolutions),
            pull_request_references=tuple(pull_request_references),
            commit_parents=tuple(commit_parents),
            commit_files=tuple(commit_files),
            developer_issues=tuple(developer_issues),
            developer_pull_requests=tuple(developer_pull_requests),
            developer_commits=tuple(developer_commits),
        )


def _properties(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _repository_relation(repository_id: int, to_key: str) -> GraphRow:
    return {"githubRepositoryId": repository_id, "toKey": to_key, "properties": {}}


def _change_properties(file: Any) -> dict[str, Any]:
    return _properties(
        status=file.status,
        additions=file.additions,
        deletions=file.deletions,
        changes=file.changes,
        previousPath=(
            normalize_repository_path(file.previous_filename)
            if file.previous_filename is not None
            else None
        ),
    )
