"""Neo4j 코드 그래프 탐색(traversal) Cypher 쿼리 함수 모음.

app/ai/rag/nodes/graph_retriever.py가 question_kind별로 이 중 하나를 골라
호출함. app/graph/repositories/code_graph.py는 "저장"만 담당하고 "조회"
로직은 여기 없었음 — 이 파일이 그 빈틈을 채움.

노드/엣지 저장 컨벤션 재확인 (app/graph/mappings.py, app/graph/repositories/
code_graph.py 참고, 2026-08-22 MethodVersion 스키마 반영 후 기준):
- 모든 노드는 MERGE (node:Label {key: ...})로 저장됨. key 속성이 곧
  graph_node_id/method_node_id — 탐색 시작점은 항상 이 key로 찾는다:
  MATCH (start {key: $start_node_id})
- Method(불변 정체성) 속성: name, signature, class_name (snake_case)
- MethodVersion(버전 스냅샷) 속성: methodKey, contentHash, sourceCode,
  startLine, endLine (camelCase — Method와 네이밍 컨벤션이 다름, 팀
  컨벤션 통일 여부는 그래프 담당자 확인 필요)
- 관계: CONTAINS(Class->Method), HAS_VERSION(Method->MethodVersion),
  CALLS(MethodVersion->Method, 항상 버전에서 출발해서 메서드로 도착),
  INTRODUCED_IN(MethodVersion->Commit), DELETED_IN(Method->Commit),
  EXPOSES(Method->Endpoint), EXTENDS/IMPLEMENTS/IMPORTS/MANAGES
  (app/graph/repositories/code_graph.py의 ALLOWED_RELATIONSHIP_TYPES)

## 2026-08-22 업데이트 (MethodVersion 스키마 반영, 4개 함수 전부 재작성)

배경은 docs/qa_retrieval_part_plan.md의 "0-2" 섹션 참고. 요약:
`CALLS`가 `(MethodVersion)-[:CALLS]->(Method)` 형태로 바뀌면서(출발은 버전,
도착은 메서드), 예전처럼 `CALLS` 하나만 타고 여러 홉을 가는 게 안 됨 —
Method에는 나가는 CALLS가 없고(그건 그 Method의 MethodVersion에만 있음),
그래서 2홉째부터 항상 끊겼음.

- calls_forward / calls_backward: `CALLS`와 `HAS_VERSION`을 번갈아 타도록
  `[:CALLS|HAS_VERSION*1..N]`로 바꿈. "논리적 호출 1홉"이 그래프 상으로는
  `CALLS`+`HAS_VERSION` 2홉이라서 depth를 2배로 잡음(`depth * 2`). 완벽한
  근사는 아님 — 같은 Method의 다른(형제) 버전이 결과에 섞여 들어올 수
  있음. 실 데이터로 결과 품질 확인 후 필요하면 조정할 것.
- changed_by_history: 원래 계획이던 `CHANGED_BY` 관계(별도 배치 작업 필요,
  그래프 담당자 승인 대기 상태였음)를 실제로 만들지 않고, 팀원이 이미
  만들어 둔 `HAS_VERSION`/`INTRODUCED_IN`/`DELETED_IN`을 읽는 것으로
  완전히 교체함. 새 관계 타입을 그래프에 쓰는 게 아니라 이미 있는 걸 읽기만
  하므로 그래프 담당자 승인 불필요.

구현 (docs/langgraph_pipeline.md 4.6, 2.2 / docs/qa_retrieval_part_plan.md
Step 3 참고):

- depth는 f-string으로 쿼리에 직접 넣음(가변 길이 경로는 파라미터 바인딩이
  안 되는 Cypher 자체 제약). depth는 사용자 입력이 아니라 코드 상수라
  인젝션 위험 없음.
- _path_to_graph_dict(records): 공통 변환 헬퍼. 각 레코드의 모든 값 중
  "path처럼 생긴" 값(.nodes/.relationships 속성을 가진 값 — 실제
  neo4j.graph.Path와 duck-typing으로 호환, 테스트에서 가짜 객체로 대체하기
  쉽게 isinstance 대신 hasattr로 판별)을 찾아서 그 안의 노드/관계를
  app.dtos.chat.GraphData 호환 {"nodes": [...], "edges": [...]}로 합침.
  - node.type: Endpoint는 "api", Commit은 "commit", MethodVersion은
    "method_version", Method는 "method", Interface는 "interface", Class는
    "class"(그 외는 방어적으로 "symbol"). **2026-08-24 변경**: 전에는
    Method/MethodVersion/Class/Interface가 전부 "symbol" 하나로 뭉뚱그려져
    있었는데, FE 그래프 시각화(코드 실행 흐름)에서 노드 종류를 전혀 구분할
    수 없다는 문제가 있어서 세분화함. **⚠️ 이 값 자체가 늘어난 것만으로는
    FE에 반영 안 됨** — app/adapters/qa_response_adapter.py의
    `_GRAPH_NODE_TYPES` 화이트리스트와 app/dtos/chat.py의
    `GraphNode.type` Literal도 같이 넓혀야 실제로 API 응답까지 새 타입이
    나감(둘 다 같이 수정함, 아래 참고). evidence_fusion.py가 "commit"
    타입만 보고 Evidence.type을 매핑하므로 그 로직은 안 건드림.
  - node.label / node.detail: Method/MethodVersion/Endpoint/Commit 각각
    보기 좋은 값으로 뽑음(아래 _node_label/_node_detail 참고) — changed_by_history가
    이제 실제로 Commit 노드를 돌려주기 시작해서(예전엔 CHANGED_BY가 아예
    없어서 이 경로를 탈 일이 없었음) 추가함. **2026-08-24 변경**: MethodVersion
    라벨이 "코드 버전 (L25-178)"처럼 무슨 메서드인지 전혀 안 드러나던 문제,
    Method 라벨이 합성 module 클래스 내부 이름("server$module.createClient()")을
    그대로 노출하던 문제 둘 다 수정함(아래 _node_label 참고).
  - node.id: Neo4j의 key 속성 그대로 사용
  - key(node)/(source,type,target) 기준으로 중복 노드·엣지 제거
"""

import re

from app.clients.neo4j import Neo4jClient
from app.dtos.history_retrieval import (
    CommitHistoryMetadata,
    MethodVersionHistoryMetadata,
)

DEFAULT_CALLS_DEPTH = 5
DEFAULT_NEIGHBORHOOD_DEPTH = 2

# 2026-08-26 신규: getter/setter는 그래프 시각화에서 대부분 "부가적인" 노드라
# 오히려 흐름을 읽기 어렵게 만든다는 피드백을 받아서 걸러냄 (아래
# _is_trivial_accessor_name / _path_to_graph_dict의 keep_node_id 참고).
# "get"/"set" 뒤에 대문자·숫자가 바로 오는 것만 매치해서 "getaway"/"setup"/
# "issueRefund"같은 일반 단어는 안 걸리게 함.
_TRIVIAL_ACCESSOR_NAME_PATTERN = re.compile(r"^(get|set|is)[A-Z0-9]")


def calls_forward(
    client: Neo4jClient, start_node_id: str, depth: int = DEFAULT_CALLS_DEPTH
) -> dict:
    """flow: CALLS(+HAS_VERSION으로 버전<->메서드 건너뛰기)를 depth까지 순방향 탐색."""
    query = f"""
    MATCH path =
      (start {{key: $start_node_id}})-[:CALLS|HTTP_CALLS|HAS_VERSION*1..{depth * 2}]->(end)
    OPTIONAL MATCH owner_path =
      (:Method)-[:HAS_VERSION]->(start)
    OPTIONAL MATCH start_endpoint_path =
      (:Endpoint)<-[:EXPOSES]-(:Method)-[:HAS_VERSION]->(start)
    OPTIONAL MATCH endpoint_path =
      (start)-[:CALLS|HTTP_CALLS|HAS_VERSION*1..{depth * 2}]->
      (:Endpoint)<-[:EXPOSES]-(controller:Method)
    OPTIONAL MATCH downstream_path =
      (controller)-[:HAS_VERSION]->(:MethodVersion)
      -[:CALLS|HAS_VERSION*1..{depth * 2}]->(downstream)
    RETURN path, owner_path, start_endpoint_path, endpoint_path, downstream_path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records, keep_node_id=start_node_id)


def calls_backward(
    client: Neo4jClient, start_node_id: str, depth: int = DEFAULT_CALLS_DEPTH
) -> dict:
    """impact: CALLS 역방향 — 누가 이 메서드를 호출하는지. start_node_id는 반드시
    method_node_id(Method key)여야 함 — CALLS의 도착점이 항상 Method라서, 버전
    key(graph_node_id)를 넘기면 매치가 하나도 안 돼 항상 빈 결과가 나옴."""
    query = f"""
    MATCH path =
      (caller)-[:CALLS|HAS_VERSION*1..{depth * 2}]->
      (start:Method {{key: $start_node_id}})
    RETURN path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records, keep_node_id=start_node_id)


def shallow_neighborhood(
    client: Neo4jClient, start_node_id: str, depth: int = DEFAULT_NEIGHBORHOOD_DEPTH
) -> dict:
    """location: 관계 타입 제한 없이 depth까지만 얕게 탐색. start_node_id는
    method_node_id 권장 — Method 기준이어야 소속 Class(CONTAINS 역방향),
    API 엔드포인트(EXPOSES) 같은 "위치" 정보가 한 홉 안에 들어옴."""
    query = f"""
    MATCH path = (start {{key: $start_node_id}})-[*1..{depth}]-(neighbor)
    RETURN path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records, keep_node_id=start_node_id)


def changed_by_history(client: Neo4jClient, start_node_id: str) -> dict:
    """intent: 이 메서드가 어느 커밋들에서 바뀌어 왔는지. start_node_id는
    method_node_id(Method key)여야 함.

    Method-[:HAS_VERSION]->MethodVersion-[:INTRODUCED_IN]->Commit 으로 이
    메서드의 모든 버전이 각각 어느 커밋에서 만들어졌는지 훑고, 삭제된
    적 있으면 Method-[:DELETED_IN]->Commit도 같이 가져옴. Commit 노드는
    GitHub 이력 그래프와 key가 같은 노드를 공유하므로(app/graph/mappers/github.py,
    app/graph/mappings.py 둘 다 repository_scoped_key(repo_id, "commit", sha)
    사용 확인함), scripts/import_github_history.py가 실행된 레포라면 커밋
    메시지/작성자 등 추가 정보도 이 Commit 노드에 이미 붙어 있을 수 있음.
    """
    query = """
    MATCH (start:Method {key: $start_node_id})
    OPTIONAL MATCH history = (start)-[:HAS_VERSION]->(:MethodVersion)-[:INTRODUCED_IN]->(:Commit)
    OPTIONAL MATCH deletion = (start)-[:DELETED_IN]->(:Commit)
    RETURN history, deletion
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(
        result.records, include_history_metadata=True, keep_node_id=start_node_id
    )


def _looks_like_path(value) -> bool:
    """neo4j.graph.Path와 duck-typing으로 호환되는 값인지 판별.

    isinstance(value, neo4j.graph.Path) 대신 hasattr로 판별하는 이유: 실제
    Path/Node/Relationship은 드라이버 내부에서만 생성 가능해서, 단위
    테스트에서 이 판별 로직을 그대로 검증하려면 같은 인터페이스(.nodes/
    .relationships)를 가진 가짜 객체로 대체할 수 있어야 함.
    """
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def _node_type(node) -> str:
    """FE 배지/아이콘 분기용 노드 종류. 2026-08-24: "symbol" 하나로 뭉치던
    걸 세분화함 — 화면에서 Method/MethodVersion/Class/Interface가 전부 같은
    "SYMBOL" 배지로 나와서 서로 구분이 안 되는 문제가 있었음. 이 값을
    바꾸면 app/adapters/qa_response_adapter.py의 _GRAPH_NODE_TYPES /
    app/dtos/chat.py의 GraphNode.type Literal도 같이 넓혀야 실제 API
    응답에 반영됨(같이 수정함).
    """
    labels = node.labels
    if "Endpoint" in labels:
        return "api"
    if "Commit" in labels:
        return "commit"
    if "MethodVersion" in labels:
        return "method_version"
    if "Method" in labels:
        return "method"
    if "Interface" in labels:
        return "interface"
    if "Class" in labels:
        return "class"
    if "File" in labels:
        return "file"
    if "Package" in labels:
        return "package"
    return "symbol"


def _display_class_name(class_name: str | None) -> str | None:
    """클래스 이름에서 합성 module 클래스 접미어("$module")를 벗겨냄.

    JS/Python/TS 파서가 클래스 밖 최상위 함수를 그래프 스키마에 맞추려고
    파일당 "{파일이름}$module"이라는 내부 전용 이름을 붙이는데(app/parsers/
    languages/{javascript,python,typescript}.py), 이게 그대로 화면에 노출되면
    "server$module.createClient()"처럼 사용자한테 의미 없는 내부 구현
    디테일이 새어나감. 접미어만 떼면 "server.createClient()"가 돼서 어느
    파일 소속인지는 여전히 구분되면서 내부 네이밍은 안 드러남.
    """
    if not class_name:
        return None
    stripped = class_name.removesuffix("$module")
    return stripped or None


def _node_label(node, method_version_owner: dict | None = None) -> str:
    """method_version_owner: MethodVersion.key -> {"name", "class_name"}.

    MethodVersion 노드 자체엔 메서드 이름이 없고(부모 Method 노드에만 있음),
    2026-08-24 전에는 그래서 "코드 버전 (L25-178)"처럼 무슨 메서드의 버전인지
    전혀 안 드러났음. calls_forward/calls_backward/changed_by_history가
    반환하는 경로엔 HAS_VERSION(Method->MethodVersion) 관계가 이미 포함돼
    있으므로, _path_to_graph_dict가 그 관계들을 먼저 훑어서 이 매핑을 만들어
    넘겨주면(없으면 예전처럼 라인 번호만 나오는 것으로 안전하게 폴백) 여기서
    "createClient() (L25-178)"처럼 실제 이름을 붙일 수 있음.
    """
    labels = node.labels
    if "Endpoint" in labels:
        return f"{node.get('http_method', '')} {node.get('path', '')}".strip()
    if "Method" in labels:
        display_class = _display_class_name(node.get("class_name"))
        name = node.get("name", "")
        return f"{display_class}.{name}" if display_class else name
    if "MethodVersion" in labels:
        start_line = node.get("startLine")
        end_line = node.get("endLine")
        line_range = f"L{start_line}-{end_line}" if start_line is not None else None

        owner = (method_version_owner or {}).get(node.get("key"))
        if owner:
            display_class = _display_class_name(owner.get("class_name"))
            owner_name = owner.get("name") or ""
            qualified = f"{display_class}.{owner_name}" if display_class else owner_name
            if qualified:
                return f"{qualified}() ({line_range})" if line_range else f"{qualified}()"

        return f"코드 버전 ({line_range})" if line_range else "코드 버전"
    if "Commit" in labels:
        sha = node.get("sha", "")
        return sha[:8] if sha else node.get("key", "")
    if "File" in labels:
        # File 노드엔 "name" 프로퍼티가 없고 "path"만 있어서(app/graph/mappings.py
        # 참고), 이 분기가 없으면 아래 최종 폴백(node.get("name") or node.get("key"))이
        # 둘 다 실패해서 내부 그래프 key(예: "123231656:file:...")가 그대로
        # 라벨로 노출되는 문제가 있었음(2026-08-24 발견) — 파일명만 보여줌
        # (전체 경로는 _node_detail에 남겨서 필요하면 볼 수 있게 함).
        path = node.get("path", "")
        return path.rsplit("/", 1)[-1] if path else node.get("key", "")
    return node.get("name") or node.get("key", "")


def _node_detail(node) -> str | None:
    labels = node.labels
    if "Method" in labels:
        return node.get("signature")
    if "MethodVersion" in labels:
        return node.get("methodKey")
    if "Class" in labels or "Interface" in labels:
        return node.get("path")
    if "Commit" in labels:
        return node.get("sha")
    if "File" in labels:
        return node.get("path")
    return None


def _node_metadata(node) -> dict:
    """LLM 이력 컨텍스트가 사용할 원본 속성을 손실 없이 정규화한다."""
    labels = node.labels
    if "MethodVersion" in labels:
        return MethodVersionHistoryMetadata(
            method_key=node.get("methodKey", ""),
            source_code=node.get("sourceCode", ""),
            start_line=node.get("startLine", 0),
            end_line=node.get("endLine", 0),
            content_hash=node.get("contentHash", ""),
            api_http_method=node.get("httpMethod"),
            api_path=node.get("apiPath"),
        ).model_dump(exclude_none=True)
    if "Commit" in labels:
        return CommitHistoryMetadata(
            sha=node.get("sha", ""),
            message=node.get("message"),
            author=node.get("authorName"),
            authored_at=node.get("authoredAt"),
            committed_at=node.get("committedAt"),
            url=node.get("url"),
        ).model_dump(exclude_none=True)
    return {}


def _to_graph_node(
    node, *, include_history_metadata: bool, method_version_owner: dict | None = None
) -> dict:
    return {
        "id": node.get("key"),
        "type": _node_type(node),
        "label": _node_label(node, method_version_owner),
        "detail": _node_detail(node),
        "metadata": _node_metadata(node) if include_history_metadata else {},
    }


def _is_ambiguous_call(relationship) -> bool:
    """app/graph/mappings.py의 resolve_cross_file_references()가 이름만으로는
    호출 대상을 하나로 못 좁혔을 때 "ambiguous": True 속성과 함께 후보 전부에
    CALLS/HTTP_CALLS 엣지를 만들어 둔 것인지 판별한다.

    app/ai/rag/nodes/evidence_enricher.py가 이미 같은 기준으로 이런 엣지를
    답변 근거에서 제외하고 있음 — 그래프 시각화도 같은 기준을 따르게 해서
    "ChatMessageStore.get()이 RepositoryStore.get()을 호출한다"처럼 실제로는
    확인되지 않은 관계가 그림으로만 새어나가는 걸 막는다.
    """
    return hasattr(relationship, "get") and relationship.get("ambiguous") is True


def _to_graph_edge(relationship) -> dict:
    source_key = relationship.start_node.get("key")
    target_key = relationship.end_node.get("key")
    edge = {
        "id": f"{source_key}-{relationship.type}-{target_key}",
        "source": source_key,
        "target": target_key,
        "type": relationship.type,
        "label": relationship.type,
    }
    properties = dict(relationship.items()) if hasattr(relationship, "items") else {}
    if properties:
        edge["metadata"] = properties
    return edge


def _is_trivial_accessor_name(name: str | None) -> bool:
    """Java Bean 스타일 getter/setter(및 boolean is-getter) 이름인지 판별."""
    return bool(name) and bool(_TRIVIAL_ACCESSOR_NAME_PATTERN.match(name))


def _effective_method_name(node, method_version_owner: dict | None) -> str | None:
    """노드가 getter/setter인지 판단할 때 쓸 "실제 메서드 이름".

    Method 노드는 자기 name을 그대로 쓰고, MethodVersion은 자기 이름이 없어서
    (_node_label과 동일하게) HAS_VERSION으로 연결된 부모 Method의 이름을
    빌려온다. 그 외 노드 타입(Class/Endpoint/Commit/File/...)은 애초에
    getter/setter 판별 대상이 아니므로 None을 반환해서 필터링 대상에서 제외.
    """
    labels = node.labels
    if "Method" in labels:
        return node.get("name")
    if "MethodVersion" in labels:
        owner = (method_version_owner or {}).get(node.get("key"))
        return owner.get("name") if owner else None
    return None


def _collect_method_version_owners(records: list) -> dict:
    """모든 경로의 HAS_VERSION(Method->MethodVersion) 관계를 먼저 훑어서
    "이 MethodVersion이 누구의 버전인지"(이름 + 클래스) 매핑을 만든다.

    _node_label이 MethodVersion 라벨을 만들 때 참고함. calls_forward/
    calls_backward가 [:CALLS|HAS_VERSION*] 경로를 통째로 반환하기 때문에,
    반환된 MethodVersion의 부모 Method는 보통 같은 경로 안에 이미 있음 —
    별도 쿼리 없이 이미 받은 데이터에서 조립 가능.
    """
    owners: dict[str, dict] = {}
    for record in records:
        for value in record.values():
            if value is None or not _looks_like_path(value):
                continue
            for relationship in value.relationships:
                if relationship.type != "HAS_VERSION":
                    continue
                version_key = relationship.end_node.get("key")
                if not version_key or version_key in owners:
                    continue
                method_node = relationship.start_node
                owners[version_key] = {
                    "name": method_node.get("name", ""),
                    "class_name": method_node.get("class_name"),
                }
    return owners


def _path_to_graph_dict(
    records: list,
    *,
    include_history_metadata: bool = False,
    keep_node_id: str | None = None,
) -> dict:
    """Neo4j 쿼리 결과 레코드 리스트를 GraphData 호환 {"nodes", "edges"} dict로 변환.

    keep_node_id: 이 탐색의 시작 노드 key. getter/setter 필터링(아래 참고)
    대상이더라도 사용자가 직접 물어본 대상이면 무조건 남긴다 — 예를 들어
    "getCurrentUser() 흐름을 알려줘"처럼 시작점 자체가 getter인 질문에서까지
    그 노드가 사라지면 안 되기 때문.

    2026-08-26 신규: getter/setter(Method/MethodVersion 한정, 이름이
    "get"/"set"/"is" + 대문자·숫자로 시작하는 패턴 — _is_trivial_accessor_name
    참고)는 대부분 실행 흐름의 "부가적인" 노드라 그래프를 오히려 읽기 어렵게
    만든다는 피드백을 받아서 결과에서 제외한다. 노드를 지우면 그 노드에 걸린
    엣지도 같이 끊어지므로(예: A -> getB() -> C였다면 A-C 사이 연결 자체가
    사라짐), 이건 의도적으로 감수하는 손실이다 — "정확한 전체 그래프"보다
    "읽기 쉬운 요약"을 우선한 선택. 실 데이터로 확인해서 너무 많이 끊긴다
    싶으면 조정할 것.

    2026-08-26 신규 (같은 날 두 번째 발견): "ChatMessageStore.get() ->
    RepositoryStore.get() -> ChatSessionStore.get()"처럼 서로 무관한 클래스의
    동명 메서드끼리 CALLS로 잘못 이어져서 반복적으로 나타나는 문제를 사용자가
    스크린샷으로 제보함. 원인은 이 파일이 아니라 app/graph/mappings.py의
    resolve_cross_file_references()(그래프 담당 팀원 파일)에 있음 — CALLS
    호출 대상 이름이 "get"처럼 아주 흔하고, 호출부의 리시버 타입을 모르는
    경우(예: self._session.get(...)처럼 외부 라이브러리 객체에 대한 호출이라
    receiver_type을 못 알아낸 경우) 같은 이름의 메서드 *전부*를 후보로 남겨
    "ambiguous": True 속성과 함께 전부 CALLS 엣지로 이어버림(하나로 못 좁히는
    것보다 넓게라도 남기는 게 낫다는 절충 — mappings.py 자체 주석 참고). 이
    속성은 Neo4j 관계에 그대로 저장됨(app/graph/repositories/code_graph.py의
    `SET relation += row.properties`).
    app/ai/rag/nodes/evidence_enricher.py는 이미 이 "ambiguous" 관계를 신뢰할
    수 없다고 보고 답변 근거 텍스트에서 제외하고 있었는데(LLM이 만드는 답변
    문장은 그래서 이 오류가 안 보임), 그래프 *시각화* 경로(이 파일)는 같은
    체크가 없어서 근거 텍스트와 달리 화면에는 그대로 새어나가고 있었음 — 그
    불일치를 여기서 맞춤. mappings.py의 해석 알고리즘 자체(그래프 담당
    팀원 소유)는 안 건드리고, 이미 Neo4j에 저장된 "ambiguous" 신호를 내
    파일에서 한 번 더 걸러내는 방식으로 고침(evidence_enricher.py와 동일한
    기준, 최소 침습).
    """
    nodes_by_id: dict[str, dict] = {}
    edges_by_key: dict[tuple, dict] = {}
    method_version_owner = _collect_method_version_owners(records)

    for record in records:
        for value in record.values():
            if value is None or not _looks_like_path(value):
                continue
            for node in value.nodes:
                key = node.get("key")
                if not key or key in nodes_by_id:
                    continue
                if key != keep_node_id and _is_trivial_accessor_name(
                    _effective_method_name(node, method_version_owner)
                ):
                    continue
                nodes_by_id[key] = _to_graph_node(
                    node,
                    include_history_metadata=include_history_metadata,
                    method_version_owner=method_version_owner,
                )
            for relationship in value.relationships:
                if relationship.type in ("CALLS", "HTTP_CALLS") and _is_ambiguous_call(
                    relationship
                ):
                    continue
                edge_key = (
                    relationship.start_node.get("key"),
                    relationship.type,
                    relationship.end_node.get("key"),
                )
                if edge_key not in edges_by_key:
                    edges_by_key[edge_key] = _to_graph_edge(relationship)

    # getter/setter로 걸러진 노드를 가리키던 엣지는 양 끝 중 하나가
    # nodes_by_id에 없는 상태로 남으므로 여기서 같이 정리한다.
    edges = [
        edge
        for edge in edges_by_key.values()
        if edge["source"] in nodes_by_id and edge["target"] in nodes_by_id
    ]

    return {"nodes": list(nodes_by_id.values()), "edges": edges}
