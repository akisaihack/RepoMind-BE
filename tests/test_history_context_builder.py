"""Development-history context composition tests."""

from app.ai.generation.history_context_builder import HistoryContextBuilder
from app.ai.rag.evidence_ids import evidence_id


def _method_node() -> dict:
    return {
        "id": "method:authenticate",
        "type": "symbol",
        "label": "AuthController.authenticateUser",
        "metadata": {},
    }


def _version_node(
    node_id: str,
    source: str,
    content_hash: str,
    start_line: int,
) -> dict:
    return {
        "id": node_id,
        "type": "symbol",
        "label": f"코드 버전 (L{start_line}-{start_line + 4})",
        "detail": "1:class:src/AuthController.java:com.example.AuthController:"
        "method:authenticateUser:(LoginRequest)",
        "metadata": {
            "node_type": "MethodVersion",
            "method_key": "1:class:src/AuthController.java:com.example.AuthController:"
            "method:authenticateUser:(LoginRequest)",
            "source_code": source,
            "start_line": start_line,
            "end_line": start_line + 4,
            "content_hash": content_hash,
        },
    }


def _commit_node(node_id: str, sha: str, date: str, message: str) -> dict:
    return {
        "id": node_id,
        "type": "commit",
        "label": sha[:8],
        "metadata": {
            "node_type": "Commit",
            "sha": sha,
            "message": message,
            "author": "Developer",
            "committed_at": date,
        },
    }


def _pull_request_node() -> dict:
    return {
        "id": "pr:42",
        "type": "symbol",
        "label": "#42 Prevent duplicate votes",
        "metadata": {
            "node_type": "PullRequest",
            "number": 42,
            "title": "Prevent duplicate votes",
            "body": "Reject duplicate votes from the same user.",
            "state": "closed",
            "url": "https://github.com/org/repo/pull/42",
            "merged": True,
        },
    }


def _issue_node() -> dict:
    return {
        "id": "issue:35",
        "type": "symbol",
        "label": "#35 Duplicate votes",
        "metadata": {
            "node_type": "Issue",
            "number": 35,
            "title": "Duplicate votes",
            "body": "A user can vote more than once.",
            "state": "closed",
            "url": "https://github.com/org/repo/issues/35",
            "labels": ["bug"],
        },
    }


def test_joins_versions_and_commits_chronologically_and_builds_diff() -> None:
    old_version = _version_node(
        "version:old",
        "void authenticateUser() {\n    login();\n}",
        "hash-old",
        10,
    )
    new_version = _version_node(
        "version:new",
        "void authenticateUser() {\n    validate();\n    login();\n}",
        "hash-new",
        20,
    )
    old_commit = _commit_node(
        "commit:old", "aaa111", "2026-08-01T10:00:00Z", "feat: 로그인 추가"
    )
    new_commit = _commit_node(
        "commit:new", "bbb222", "2026-08-10T10:00:00Z", "fix: 로그인 검증 추가"
    )
    nodes = [_method_node(), new_version, new_commit, old_version, old_commit]
    edges = [
        {"source": "method:authenticate", "target": "version:new", "type": "HAS_VERSION"},
        {"source": "version:new", "target": "commit:new", "type": "INTRODUCED_IN"},
        {"source": "method:authenticate", "target": "version:old", "type": "HAS_VERSION"},
        {"source": "version:old", "target": "commit:old", "type": "INTRODUCED_IN"},
    ]
    evidence = [
        {"id": evidence_id("code", "version:new")},
        {"id": evidence_id("commit", "commit:new")},
    ]

    result = HistoryContextBuilder().build(nodes, edges, evidence)

    assert [change.commit.sha for change in result] == ["aaa111", "bbb222"]
    assert result[0].change_type == "first_observed"
    assert result[1].change_type == "modified"
    assert result[1].version is not None
    assert result[1].version.path == "src/AuthController.java"
    assert result[1].version.symbol == "AuthController.authenticateUser(LoginRequest)"
    assert result[1].version.evidence_id == evidence_id("code", "version:new")
    assert result[1].commit.evidence_id == evidence_id("commit", "commit:new")
    assert result[1].diff is not None
    assert result[1].diff.previous_commit_sha == "aaa111"
    assert result[1].diff.added_lines == ["    validate();"]
    assert result[1].diff.removed_lines == []


def test_deduplicates_same_version_and_preserves_deletion() -> None:
    version = _version_node("version:1", "void run() {}", "same-hash", 10)
    commit = _commit_node("commit:1", "abc123", "2026-08-01T10:00:00Z", "feat: 추가")
    deletion = _commit_node(
        "commit:delete", "def456", "2026-08-20T10:00:00Z", "refactor: 제거"
    )
    nodes = [_method_node(), version, commit, deletion]
    edges = [
        {"source": "method:authenticate", "target": "version:1", "type": "HAS_VERSION"},
        {"source": "version:1", "target": "commit:1", "type": "INTRODUCED_IN"},
        {"source": "version:1", "target": "commit:1", "type": "INTRODUCED_IN"},
        {"source": "method:authenticate", "target": "commit:delete", "type": "DELETED_IN"},
    ]

    result = HistoryContextBuilder().build(nodes, edges)

    assert [change.change_type for change in result] == ["first_observed", "deleted"]
    assert result[1].version is None


def test_skips_incomplete_version_commit_relationship() -> None:
    result = HistoryContextBuilder().build(
        [_version_node("version:1", "void run() {}", "hash", 10)],
        [{"source": "version:1", "target": "commit:missing", "type": "INTRODUCED_IN"}],
    )

    assert result == []


def test_attaches_pull_request_and_resolved_issue_to_commit_change() -> None:
    version = _version_node("version:1", "void run() {}", "hash", 10)
    commit = _commit_node("commit:1", "abc123", "2026-08-01T10:00:00Z", "fix")
    pull_request = _pull_request_node()
    issue = _issue_node()
    evidence = [
        {"id": evidence_id("itsm", "pr:42")},
        {"id": evidence_id("itsm", "issue:35")},
    ]

    result = HistoryContextBuilder().build(
        [_method_node(), version, commit, pull_request, issue],
        [
            {"source": "method:authenticate", "target": "version:1", "type": "HAS_VERSION"},
            {"source": "version:1", "target": "commit:1", "type": "INTRODUCED_IN"},
            {"source": "pr:42", "target": "commit:1", "type": "CONTAINS_COMMIT"},
            {"source": "pr:42", "target": "issue:35", "type": "REFERENCES"},
            {"source": "pr:42", "target": "issue:35", "type": "RESOLVES"},
        ],
        evidence,
    )

    assert result[0].pull_requests[0].number == 42
    assert result[0].pull_requests[0].evidence_id == evidence_id("itsm", "pr:42")
    assert result[0].issues[0].number == 35
    assert result[0].issues[0].relation == "RESOLVES"
    assert result[0].issues[0].evidence_id == evidence_id("itsm", "issue:35")
