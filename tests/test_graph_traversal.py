"""Neo4j traversal 결과의 이력 메타데이터 보존 테스트."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.graph.queries.traversal import (
    DEFAULT_CALLS_DEPTH,
    _path_to_graph_dict,
    calls_backward,
    calls_forward,
)


class FakeNode(dict):
    def __init__(self, labels: set[str], **properties):
        super().__init__(properties)
        self.labels = labels


class FakeRelationship:
    def __init__(self, start_node, end_node, relation_type: str):
        self.start_node = start_node
        self.end_node = end_node
        self.type = relation_type


class FakePath:
    def __init__(self, nodes, relationships):
        self.nodes = nodes
        self.relationships = relationships


def test_call_traversal_uses_five_logical_depths_by_default() -> None:
    client = MagicMock()
    client.execute_query.return_value = SimpleNamespace(records=[])

    calls_forward(client, "version:start")
    forward_query = client.execute_query.call_args.args[0]
    assert DEFAULT_CALLS_DEPTH == 5
    assert "*1..10" in forward_query
    assert "owner_path" in forward_query
    assert "(:Method)-[:HAS_VERSION]->(start)" in forward_query

    calls_backward(client, "method:start")
    backward_query = client.execute_query.call_args.args[0]
    assert "*1..10" in backward_query


def test_preserves_method_version_and_commit_history_metadata() -> None:
    version = FakeNode(
        {"MethodVersion"},
        key="version:authenticate",
        methodKey="method:authenticate",
        sourceCode="String jwt = tokenProvider.generateToken(authentication);",
        startLine=23,
        endLine=36,
        contentHash="content-hash",
        httpMethod="POST",
        apiPath="/api/auth/signin",
    )
    commit = FakeNode(
        {"Commit"},
        key="commit:abc123",
        sha="abc123456789",
        message="feat: JWT 로그인 추가",
        authorName="Developer",
        authoredAt="2026-08-01T10:00:00Z",
        committedAt="2026-08-01T11:00:00Z",
        url="https://github.com/org/repo/commit/abc123456789",
    )
    relation = FakeRelationship(version, commit, "INTRODUCED_IN")

    result = _path_to_graph_dict(
        [{"history": FakePath([version, commit], [relation])}],
        include_history_metadata=True,
    )

    assert result["nodes"] == [
        {
            "id": "version:authenticate",
            "type": "symbol",
            "label": "코드 버전 (L23-36)",
            "detail": "method:authenticate",
            "metadata": {
                "node_type": "MethodVersion",
                "method_key": "method:authenticate",
                "source_code": "String jwt = tokenProvider.generateToken(authentication);",
                "start_line": 23,
                "end_line": 36,
                "content_hash": "content-hash",
                "api_http_method": "POST",
                "api_path": "/api/auth/signin",
            },
        },
        {
            "id": "commit:abc123",
            "type": "commit",
            "label": "abc12345",
            "detail": "abc123456789",
            "metadata": {
                "node_type": "Commit",
                "sha": "abc123456789",
                "message": "feat: JWT 로그인 추가",
                "author": "Developer",
                "authored_at": "2026-08-01T10:00:00Z",
                "committed_at": "2026-08-01T11:00:00Z",
                "url": "https://github.com/org/repo/commit/abc123456789",
            },
        },
    ]
    assert result["edges"] == [
        {
            "id": "version:authenticate-INTRODUCED_IN-commit:abc123",
            "source": "version:authenticate",
            "target": "commit:abc123",
            "type": "INTRODUCED_IN",
            "label": "INTRODUCED_IN",
        }
    ]


def test_omits_large_history_metadata_from_non_history_traversal() -> None:
    version = FakeNode(
        {"MethodVersion"},
        key="version:authenticate",
        methodKey="method:authenticate",
        sourceCode="large source code",
        startLine=23,
        endLine=36,
        contentHash="content-hash",
    )

    result = _path_to_graph_dict([{"path": FakePath([version], [])}])

    assert result["nodes"][0]["metadata"] == {}
