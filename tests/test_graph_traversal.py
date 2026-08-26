"""Neo4j traversal 결과의 이력 메타데이터 보존 테스트."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.graph.queries.traversal import (
    DEFAULT_CALLS_DEPTH,
    _path_to_graph_dict,
    calls_backward,
    calls_forward,
    changed_by_history,
)


class FakeNode(dict):
    def __init__(self, node_labels: set[str], **properties):
        super().__init__(properties)
        self.labels = node_labels


class FakeRelationship(dict):
    def __init__(self, start_node, end_node, relation_type: str, **properties):
        super().__init__(properties)
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


def test_history_traversal_includes_pull_requests_and_issues() -> None:
    client = MagicMock()
    client.execute_query.return_value = SimpleNamespace(records=[])

    changed_by_history(client, "method:authenticate")

    query = client.execute_query.call_args.args[0]
    assert "(history_pr:PullRequest)-[:CONTAINS_COMMIT]->(history_commit)" in query
    assert "(history_pr)-[:RESOLVES|REFERENCES]->(:Issue)" in query
    assert "(deletion_pr:PullRequest)-[:CONTAINS_COMMIT]->(deletion_commit)" in query


def test_preserves_pull_request_and_issue_history_metadata() -> None:
    commit = FakeNode({"Commit"}, key="commit:abc", sha="abc123", message="fix")
    pull_request = FakeNode(
        {"PullRequest"},
        key="pr:42",
        number=42,
        title="Prevent duplicate votes",
        body="Reject a second vote from the same user.",
        state="closed",
        url="https://github.com/org/repo/pull/42",
        merged=True,
        mergedAt="2026-08-10T10:00:00Z",
    )
    issue = FakeNode(
        {"Issue"},
        key="issue:35",
        number=35,
        title="Duplicate votes are accepted",
        body="A user can vote twice.",
        state="closed",
        url="https://github.com/org/repo/issues/35",
        labels=["bug"],
    )

    result = _path_to_graph_dict(
        [
            {
                "pull_request": FakePath(
                    [pull_request, commit],
                    [FakeRelationship(pull_request, commit, "CONTAINS_COMMIT")],
                ),
                "issue": FakePath(
                    [pull_request, issue],
                    [FakeRelationship(pull_request, issue, "RESOLVES")],
                ),
            }
        ],
        include_history_metadata=True,
    )

    nodes = {node["id"]: node for node in result["nodes"]}
    assert nodes["pr:42"]["metadata"] == {
        "node_type": "PullRequest",
        "number": 42,
        "title": "Prevent duplicate votes",
        "body": "Reject a second vote from the same user.",
        "state": "closed",
        "url": "https://github.com/org/repo/pull/42",
        "merged": True,
        "merged_at": "2026-08-10T10:00:00Z",
    }
    assert nodes["issue:35"]["metadata"]["node_type"] == "Issue"
    assert nodes["issue:35"]["metadata"]["labels"] == ["bug"]


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


def test_file_node_shows_filename_instead_of_raw_graph_key() -> None:
    # 2026-08-24 회귀 테스트 (같은 날 두 번째 라운드, "location" 질문의
    # shallow_neighborhood 결과를 FE에서 직접 확인하다가 발견함): File 노드는
    # "name" 프로퍼티가 없고 "path"만 있는데, _node_type/_node_label 둘 다
    # File을 몰라서 "symbol" 타입 + 내부 그래프 key 그대로("123231656:file:...")가
    # 라벨로 노출되던 문제.
    file_node = FakeNode(
        {"File"},
        key="123231656:file:polling-app-client/src/app/App.js",
        path="polling-app-client/src/app/App.js",
    )

    result = _path_to_graph_dict([{"path": FakePath([file_node], [])}])

    assert result["nodes"][0]["type"] == "file"
    assert result["nodes"][0]["label"] == "App.js"
    assert result["nodes"][0]["detail"] == "polling-app-client/src/app/App.js"


def test_package_node_is_typed_distinctly_from_generic_symbol() -> None:
    package_node = FakeNode({"Package"}, key="package:com.example.poll", name="com.example.poll")

    result = _path_to_graph_dict([{"path": FakePath([package_node], [])}])

    assert result["nodes"][0]["type"] == "package"
    assert result["nodes"][0]["label"] == "com.example.poll"


def test_getter_setter_methods_are_filtered_out_of_graph_nodes() -> None:
    # 2026-08-26 신규: 사용자 피드백 — getter/setter 같은 부가적인 노드는
    # 실행 흐름 그래프에서 오히려 노이즈이므로 빼달라고 함.
    caller = FakeNode({"Method"}, key="method:save", name="save", class_name="PollService")
    getter = FakeNode({"Method"}, key="method:getUsername", name="getUsername", class_name="Poll")
    calls = FakeRelationship(caller, getter, "CALLS")

    result = _path_to_graph_dict([{"path": FakePath([caller, getter], [calls])}])

    node_ids = {node["id"] for node in result["nodes"]}
    assert node_ids == {"method:save"}
    assert result["edges"] == []  # getter로 끊긴 엣지도 같이 제거됨


def test_start_node_is_kept_even_when_it_matches_getter_setter_pattern() -> None:
    # "getCurrentUser() 흐름을 알려줘"처럼 시작점 자체가 getter인 경우까지
    # 사라지면 안 됨 — keep_node_id로 예외 처리.
    getter = FakeNode(
        {"Method"}, key="method:getCurrentUser", name="getCurrentUser", class_name="AuthService"
    )
    called = FakeNode({"Method"}, key="method:findById", name="findById", class_name="UserRepo")
    calls = FakeRelationship(getter, called, "CALLS")

    result = _path_to_graph_dict(
        [{"path": FakePath([getter, called], [calls])}],
        keep_node_id="method:getCurrentUser",
    )

    node_ids = {node["id"] for node in result["nodes"]}
    assert node_ids == {"method:getCurrentUser", "method:findById"}


def test_method_version_getter_is_filtered_using_owner_name_via_has_version() -> None:
    # MethodVersion 자체엔 이름이 없어서, HAS_VERSION으로 연결된 부모 Method의
    # 이름(setPassword)을 통해 getter/setter 여부를 판단해야 함.
    caller = FakeNode({"Method"}, key="method:register", name="register", class_name="UserService")
    setter_method = FakeNode(
        {"Method"}, key="method:setPassword", name="setPassword", class_name="User"
    )
    setter_version = FakeNode({"MethodVersion"}, key="version:setPassword", startLine=1, endLine=2)
    calls_version = FakeRelationship(caller, setter_version, "CALLS")
    has_version = FakeRelationship(setter_method, setter_version, "HAS_VERSION")

    result = _path_to_graph_dict(
        [{"path": FakePath([caller, setter_version, setter_method], [calls_version, has_version])}]
    )

    node_ids = {node["id"] for node in result["nodes"]}
    assert node_ids == {"method:register"}


def test_similarly_spelled_but_non_accessor_method_names_are_not_filtered() -> None:
    # "get"/"set"/"is"로 시작하지만 실제 getter/setter가 아닌 일반 단어는
    # 걸러지면 안 됨(오탐 방지) — 뒤에 대문자/숫자가 바로 오는 것만 매치.
    getaway = FakeNode({"Method"}, key="method:getaway", name="getaway", class_name="Escape")
    issue_refund = FakeNode(
        {"Method"}, key="method:issueRefund", name="issueRefund", class_name="Billing"
    )
    setup = FakeNode({"Method"}, key="method:setup", name="setup", class_name="Fixture")

    result = _path_to_graph_dict(
        [{"path": FakePath([getaway, issue_refund, setup], [])}]
    )

    node_ids = {node["id"] for node in result["nodes"]}
    assert node_ids == {"method:getaway", "method:issueRefund", "method:setup"}


def test_ambiguous_calls_edges_are_excluded_from_graph() -> None:
    # 2026-08-26 신규: "ChatMessageStore.get() -> RepositoryStore.get() ->
    # ChatSessionStore.get()"처럼 서로 무관한 클래스의 동명 메서드끼리
    # CALLS로 잘못 이어진 채 반복적으로 나타나는 문제를 사용자가 제보함.
    # app/graph/mappings.py의 resolve_cross_file_references()가 호출 대상을
    # 하나로 못 좁히면 후보 전부에 "ambiguous": True를 달아 이어버리는데,
    # evidence_enricher.py는 이미 이런 엣지를 답변 근거에서 제외하고
    # 있었지만 그래프 시각화 경로는 같은 체크가 없어서 화면에만 새어나가고
    # 있었음 — 여기서 같은 기준으로 걸러야 함.
    message_store_get = FakeNode(
        {"Method"}, key="method:ChatMessageStore.get", name="get", class_name="ChatMessageStore"
    )
    repository_store_get = FakeNode(
        {"Method"}, key="method:RepositoryStore.get", name="get", class_name="RepositoryStore"
    )
    ambiguous_call = FakeRelationship(
        message_store_get, repository_store_get, "CALLS", ambiguous=True
    )

    result = _path_to_graph_dict(
        [{"path": FakePath([message_store_get, repository_store_get], [ambiguous_call])}]
    )

    assert result["edges"] == []


def test_unambiguous_calls_edges_are_kept() -> None:
    caller = FakeNode({"Method"}, key="method:save", name="save", class_name="PollService")
    callee = FakeNode({"Method"}, key="method:validate", name="validate", class_name="PollService")
    call = FakeRelationship(caller, callee, "CALLS", resolved=True)

    result = _path_to_graph_dict([{"path": FakePath([caller, callee], [call])}])

    assert len(result["edges"]) == 1
    assert result["edges"][0]["source"] == "method:save"
    assert result["edges"][0]["target"] == "method:validate"


def test_ambiguous_http_calls_edges_are_also_excluded() -> None:
    caller = FakeNode({"Method"}, key="method:handler", name="handler", class_name="Controller")
    endpoint = FakeNode({"Endpoint"}, key="endpoint:1", http_method="GET", path="/polls")
    ambiguous_http_call = FakeRelationship(caller, endpoint, "HTTP_CALLS", ambiguous=True)

    result = _path_to_graph_dict([{"path": FakePath([caller, endpoint], [ambiguous_http_call])}])

    assert result["edges"] == []
