"""Join MethodVersion and Commit graph data into chronological LLM history units."""

import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from difflib import ndiff

from app.ai.rag.evidence_ids import evidence_id
from app.dtos.history_context import (
    HistoryChangeContext,
    HistoryCommitContext,
    HistoryDiffContext,
    HistoryIssueContext,
    HistoryPullRequestContext,
    HistoryVersionContext,
)

_METHOD_KEY_PATTERN = re.compile(
    r"^\d+:(?:class|interface):(?P<path>.+?):(?P<owner>[^:]+):"
    r"(?:method|constructor):(?P<method>[^:]+):(?P<signature>\(.*\))$"
)


class HistoryContextBuilder:
    """Build deterministic history entries without changing visualization graph data."""

    def build(
        self,
        nodes: list[dict],
        edges: list[dict],
        evidence: list[dict] | None = None,
    ) -> list[HistoryChangeContext]:
        nodes_by_id = {
            node.get("id"): node
            for node in nodes
            if isinstance(node, Mapping) and isinstance(node.get("id"), str)
        }
        available_evidence_ids = {
            item.get("id")
            for item in evidence or []
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        }
        method_by_version: dict[str, str] = {}
        introduced_commit_by_version: dict[str, str] = {}
        deleted_commits_by_method: dict[str, list[str]] = defaultdict(list)
        pull_requests_by_commit: dict[str, set[str]] = defaultdict(set)
        issues_by_pull_request: dict[str, dict[str, str]] = defaultdict(dict)

        for edge in edges:
            if not isinstance(edge, Mapping):
                continue
            source = edge.get("source")
            target = edge.get("target")
            relation = edge.get("type")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if relation == "HAS_VERSION":
                method_by_version[target] = source
            elif relation == "INTRODUCED_IN":
                introduced_commit_by_version[source] = target
            elif relation == "DELETED_IN":
                deleted_commits_by_method[source].append(target)
            elif relation == "CONTAINS_COMMIT":
                pull_requests_by_commit[target].add(source)
            elif relation in {"RESOLVES", "REFERENCES"}:
                previous = issues_by_pull_request[source].get(target)
                if previous != "RESOLVES":
                    issues_by_pull_request[source][target] = relation

        changes_by_method: dict[str, list[HistoryChangeContext]] = defaultdict(list)
        seen_versions: set[tuple[str, str, str]] = set()
        for version_id, commit_id in introduced_commit_by_version.items():
            version_node = nodes_by_id.get(version_id)
            commit_node = nodes_by_id.get(commit_id)
            if version_node is None or commit_node is None:
                continue
            version = _version_context(
                version_node,
                available_evidence_ids,
            )
            commit = _commit_context(commit_node, available_evidence_ids)
            if version is None or commit is None:
                continue
            identity = (
                version.method_key,
                version.content_hash or version.node_id,
                commit.sha,
            )
            if identity in seen_versions:
                continue
            seen_versions.add(identity)
            method_node = nodes_by_id.get(method_by_version.get(version_id, ""), {})
            method = _method_name(method_node, version.symbol)
            pull_requests, issues = _related_work_items(
                commit_id,
                nodes_by_id,
                pull_requests_by_commit,
                issues_by_pull_request,
                available_evidence_ids,
            )
            changes_by_method[method].append(
                HistoryChangeContext(
                    method=method,
                    change_type="first_observed",
                    version=version,
                    commit=commit,
                    pull_requests=pull_requests,
                    issues=issues,
                )
            )

        result: list[HistoryChangeContext] = []
        for method, changes in changes_by_method.items():
            changes.sort(key=_history_sort_key)
            previous: HistoryChangeContext | None = None
            for change in changes:
                if previous is not None and previous.version and change.version:
                    change.change_type = "modified"
                    change.diff = _diff(previous, change)
                result.append(change)
                previous = change

            method_ids = {
                method_by_version.get(change.version.node_id, "")
                for change in changes
                if change.version is not None
            }
            for method_id in method_ids:
                for commit_id in deleted_commits_by_method.get(method_id, []):
                    commit_node = nodes_by_id.get(commit_id)
                    commit = (
                        _commit_context(commit_node, available_evidence_ids)
                        if commit_node is not None
                        else None
                    )
                    if commit is not None:
                        pull_requests, issues = _related_work_items(
                            commit_id,
                            nodes_by_id,
                            pull_requests_by_commit,
                            issues_by_pull_request,
                            available_evidence_ids,
                        )
                        result.append(
                            HistoryChangeContext(
                                method=method,
                                change_type="deleted",
                                commit=commit,
                                pull_requests=pull_requests,
                                issues=issues,
                            )
                        )

        result.sort(key=_history_sort_key)
        return result


def _version_context(
    node: Mapping,
    available_evidence_ids: set[str],
) -> HistoryVersionContext | None:
    metadata = node.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("node_type") != "MethodVersion":
        return None
    node_id = node.get("id")
    method_key = metadata.get("method_key")
    source_code = metadata.get("source_code")
    if not all(isinstance(value, str) for value in (node_id, method_key, source_code)):
        return None
    parsed = _parse_method_key(method_key)
    expected_evidence_id = evidence_id("code", node_id)
    return HistoryVersionContext(
        node_id=node_id,
        method_key=method_key,
        path=parsed[0] if parsed else None,
        symbol=parsed[1] if parsed else method_key,
        source_code=source_code,
        start_line=_integer(metadata.get("start_line")),
        end_line=_integer(metadata.get("end_line")),
        content_hash=_string(metadata.get("content_hash")),
        evidence_id=(
            expected_evidence_id if expected_evidence_id in available_evidence_ids else None
        ),
    )


def _commit_context(
    node: Mapping,
    available_evidence_ids: set[str],
) -> HistoryCommitContext | None:
    metadata = node.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("node_type") != "Commit":
        return None
    node_id = node.get("id")
    sha = metadata.get("sha")
    if not isinstance(node_id, str) or not isinstance(sha, str) or not sha:
        return None
    expected_evidence_id = evidence_id("commit", node_id)
    return HistoryCommitContext(
        node_id=node_id,
        sha=sha,
        message=_optional_string(metadata.get("message")),
        author=_optional_string(metadata.get("author")),
        authored_at=_optional_string(metadata.get("authored_at")),
        committed_at=_optional_string(metadata.get("committed_at")),
        url=_optional_string(metadata.get("url")),
        evidence_id=(
            expected_evidence_id if expected_evidence_id in available_evidence_ids else None
        ),
    )


def _related_work_items(
    commit_id: str,
    nodes_by_id: Mapping[str, Mapping],
    pull_requests_by_commit: Mapping[str, set[str]],
    issues_by_pull_request: Mapping[str, dict[str, str]],
    available_evidence_ids: set[str],
) -> tuple[list[HistoryPullRequestContext], list[HistoryIssueContext]]:
    pull_requests: list[HistoryPullRequestContext] = []
    issues_by_id: dict[str, HistoryIssueContext] = {}
    for pull_request_id in sorted(pull_requests_by_commit.get(commit_id, set())):
        node = nodes_by_id.get(pull_request_id)
        pull_request = _pull_request_context(node, available_evidence_ids) if node else None
        if pull_request is None:
            continue
        pull_requests.append(pull_request)
        for issue_id, relation in issues_by_pull_request.get(pull_request_id, {}).items():
            issue_node = nodes_by_id.get(issue_id)
            issue = (
                _issue_context(issue_node, relation, available_evidence_ids)
                if issue_node
                else None
            )
            if issue is None:
                continue
            existing = issues_by_id.get(issue_id)
            if existing is None or issue.relation == "RESOLVES":
                issues_by_id[issue_id] = issue

    pull_requests.sort(key=lambda item: item.number)
    issues = sorted(
        issues_by_id.values(),
        key=lambda item: (item.relation != "RESOLVES", item.number),
    )
    return pull_requests, issues


def _pull_request_context(
    node: Mapping, available_evidence_ids: set[str]
) -> HistoryPullRequestContext | None:
    metadata = node.get("metadata")
    node_id = node.get("id")
    if not isinstance(metadata, Mapping) or metadata.get("node_type") != "PullRequest":
        return None
    number = metadata.get("number")
    title = metadata.get("title")
    if not isinstance(node_id, str) or not isinstance(number, int) or not isinstance(title, str):
        return None
    expected_evidence_id = evidence_id("itsm", node_id)
    return HistoryPullRequestContext(
        node_id=node_id,
        number=number,
        title=title,
        body=_optional_string(metadata.get("body")),
        state=_optional_string(metadata.get("state")),
        url=_optional_string(metadata.get("url")),
        merged=metadata.get("merged") if isinstance(metadata.get("merged"), bool) else None,
        merged_at=_optional_string(metadata.get("merged_at")),
        evidence_id=(
            expected_evidence_id if expected_evidence_id in available_evidence_ids else None
        ),
    )


def _issue_context(
    node: Mapping,
    relation: str,
    available_evidence_ids: set[str],
) -> HistoryIssueContext | None:
    metadata = node.get("metadata")
    node_id = node.get("id")
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("node_type") != "Issue"
        or relation not in {"RESOLVES", "REFERENCES"}
    ):
        return None
    number = metadata.get("number")
    title = metadata.get("title")
    if not isinstance(node_id, str) or not isinstance(number, int) or not isinstance(title, str):
        return None
    raw_labels = metadata.get("labels")
    labels = (
        [item for item in raw_labels if isinstance(item, str)]
        if isinstance(raw_labels, list)
        else []
    )
    expected_evidence_id = evidence_id("itsm", node_id)
    return HistoryIssueContext(
        node_id=node_id,
        number=number,
        title=title,
        relation=relation,
        body=_optional_string(metadata.get("body")),
        state=_optional_string(metadata.get("state")),
        url=_optional_string(metadata.get("url")),
        labels=labels,
        evidence_id=(
            expected_evidence_id if expected_evidence_id in available_evidence_ids else None
        ),
    )


def _diff(
    previous: HistoryChangeContext,
    current: HistoryChangeContext,
) -> HistoryDiffContext:
    previous_version = previous.version
    current_version = current.version
    assert previous_version is not None and current_version is not None
    added: list[str] = []
    removed: list[str] = []
    for line in ndiff(
        previous_version.source_code.splitlines(),
        current_version.source_code.splitlines(),
    ):
        content = line[2:]
        if not content.strip():
            continue
        if line.startswith("+ "):
            added.append(content)
        elif line.startswith("- "):
            removed.append(content)
    return HistoryDiffContext(
        previous_commit_sha=previous.commit.sha,
        previous_content_hash=previous_version.content_hash or None,
        added_lines=added,
        removed_lines=removed,
    )


def _parse_method_key(method_key: str) -> tuple[str, str] | None:
    match = _METHOD_KEY_PATTERN.match(method_key)
    if match is None:
        return None
    class_name = match.group("owner").rsplit(".", 1)[-1]
    symbol = f"{class_name}.{match.group('method')}{match.group('signature')}"
    return match.group("path"), symbol


def _method_name(node: Mapping, fallback: str) -> str:
    label = node.get("label")
    return label if isinstance(label, str) and label else fallback


def _history_sort_key(change: HistoryChangeContext) -> tuple[bool, datetime, str]:
    raw_date = change.commit.committed_at or change.commit.authored_at
    parsed = _parse_datetime(raw_date)
    return parsed is None, parsed or datetime.max, change.commit.sha


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _integer(value: object) -> int:
    return value if isinstance(value, int) else 0


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


__all__ = ["HistoryContextBuilder"]
