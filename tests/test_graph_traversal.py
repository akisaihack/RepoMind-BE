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
            "type": "method_version",
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


def test_node_type_distinguishes_method_and_method_version_and_class_kinds() -> None:
    # 2026-08-24 회귀 테스트: 전에는 Method/MethodVersion/Class/Interface가
    # 전부 "symbol" 하나로 뭉쳐 나와서 FE에서 노드 종류를 구분할 수 없었음.
    method = FakeNode({"Method"}, key="method:save", name="save", class_name="PollService")
    version = FakeNode({"MethodVersion"}, key="version:save", startLine=1, endLine=2)
    klass = FakeNode({"Class"}, key="class:PollService")
    interface = FakeNode({"Interface"}, key="interface:Comparable")
    endpoint = FakeNode({"Endpoint"}, key="endpoint:1", http_method="GET", path="/polls")
    commit = FakeNode({"Commit"}, key="commit:1", sha="abcdef1234")

    result = _path_to_graph_dict(
        [{"path": FakePath([method, version, klass, interface, endpoint, commit], [])}]
    )

    types_by_id = {node["id"]: node["type"] for node in result["nodes"]}
    assert types_by_id == {
        "method:save": "method",
        "version:save": "method_version",
        "class:PollService": "class",
        "interface:Comparable": "interface",
        "endpoint:1": "api",
        "commit:1": "commit",
    }


def test_method_label_strips_synthetic_module_class_suffix() -> None:
    # JS/Python/TS 파서가 최상위(클래스 밖) 함수를 감싸려고 붙이는 합성
    # "{파일이름}$module" 클래스 이름이 그대로 노출되던 문제 회귀 테스트
    # ("server$module.createClient()"처럼 내부 네이밍이 새어나갔었음).
    method = FakeNode(
        {"Method"}, key="method:createClient", name="createClient", class_name="server$module"
    )

    result = _path_to_graph_dict([{"path": FakePath([method], [])}])

    # 괄호는 여기서 안 붙임 — CALL_FLOW 시각화 경로에서는
    # app/visualization/call_flow_builder.py가 이름 끝에 ")"가 없으면
    # "()"를 따로 붙여줌(기존 동작 그대로 유지, 이 테스트는 $module 접미어
    # 제거만 검증함).
    assert result["nodes"][0]["label"] == "server.createClient"


def test_method_version_label_includes_owning_method_name_via_has_version() -> None:
    # 2026-08-24 회귀 테스트: MethodVersion 노드 자체엔 이름이 없어서
    # "코드 버전 (L25-178)"처럼 무슨 메서드의 버전인지 전혀 안 드러나던 문제.
    # calls_forward/calls_backward가 반환하는 경로엔 HAS_VERSION(Method->
    # MethodVersion)이 같이 들어있으므로, 그 관계에서 이름을 끌어와야 함.
    method = FakeNode(
        {"Method"}, key="method:createClient", name="createClient", class_name="server$module"
    )
    version = FakeNode({"MethodVersion"}, key="version:createClient", startLine=25, endLine=178)
    called = FakeNode({"Method"}, key="method:connect", name="connect", class_name=None)
    has_version = FakeRelationship(method, version, "HAS_VERSION")
    calls = FakeRelationship(version, called, "CALLS")

    result = _path_to_graph_dict(
        [{"path": FakePath([method, version, called], [has_version, calls])}]
    )

    labels_by_id = {node["id"]: node["label"] for node in result["nodes"]}
    assert labels_by_id["version:createClient"] == "server.createClient() (L25-178)"


def test_method_version_label_falls_back_when_owner_not_in_same_path() -> None:
    # 부모 Method가 같은 경로 안에 없으면(예: HAS_VERSION 없이 MethodVersion만
    # 단독으로 반환되는 경우) 예전처럼 라인 번호만 보여주는 것으로 안전하게
    # 폴백해야 함 — 회귀 방지.
    version = FakeNode({"MethodVersion"}, key="version:orphan", startLine=5, endLine=9)

    result = _path_to_graph_dict([{"path": FakePath([version], [])}])

    assert result["nodes"][0]["label"] == "코드 버전 (L5-9)"
