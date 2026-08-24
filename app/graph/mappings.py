"""파서 결과(JavaFileResult 등)를 그래프 노드/엣지(GraphNode/GraphEdge)로
변환하는 순수 변환 로직.

DB(Neo4j) 접근은 전혀 하지 않음 — 실제로 저장하는 쿼리는
app/graph/repositories/에 있음. 이 모듈은 "파싱 결과를 어떤 노드/엣지
모양으로 바꿀지"만 책임짐.

## 2단계 변환 (CALLS/EXTENDS/IMPLEMENTS/MANAGES가 이름만으로는 못 끝나는 이유)

파일 하나만 보고는 `extends Foo`의 Foo가 같은 프로젝트의 어느 클래스인지,
메서드 안에서 부른 `save(...)`가 정확히 어느 클래스의 save 메서드인지 알 수
없음(다른 파일에 있을 수도 있어서). 그래서 변환을 2단계로 나눔.

1. `map_java_file()` — 파일 하나를 노드/엣지로 변환. CALLS/EXTENDS/
   IMPLEMENTS/IMPORTS/MANAGES 엣지의 target은 일단 "이름 문자열"로
   채워두고 `properties["resolved"] = False`로 표시함.
2. `resolve_cross_file_references()` — 프로젝트의 모든 파일을 변환한
   GraphDocument를 다 모은 뒤에 호출. 전체 노드를 대상으로 이름 인덱스를
   만들어서, resolved=False인 엣지들의 target을 실제 노드 id로 바꿈.

이름만으로 매칭하기 때문에 완벽하지 않음:
- 같은 이름의 메서드/클래스가 여러 개면(오버로딩, 우연히 이름이 겹치는
  별개 클래스 등) 후보 전부에 엣지를 만들고 `ambiguous=True`로 표시함.
- 매칭되는 게 하나도 없으면(JDK/외부 라이브러리 호출, 와일드카드 import
  등) 원래 이름을 target으로 남겨두고 `external=True`로 표시함.
"""

from collections.abc import Iterable

from app.dtos.analysis import (
    JavaClassResult,
    JavaFileResult,
    JavaMethodResult,
    JavaScriptFileResult,
    PythonFileResult,
    TypeScriptFileResult,
)
from app.dtos.graph import GraphDocument, GraphEdge, GraphNode
from app.dtos.protocols import ClassResultProtocol, FileResultProtocol, MethodResultProtocol
from app.graph.identifiers import (
    class_key,
    constructor_key,
    file_key,
    java_qualified_name,
    method_content_hash,
    method_key,
    method_version_key,
    normalize_repository_path,
    repository_scoped_key,
)

# ---------- 노드 ID 생성 ----------
#
# Class/Interface는 정규화된 파일 경로와 FQN, Method는 소속 Class ID와
# 이름/파라미터 시그니처로 식별한다. 선언 순서와 라인 이동은 ID에 영향을
# 주지 않는다. 실제 포맷은 graph.identifiers의 공통 함수를 사용해 청크의
# graph_node_id와 항상 일치시킨다.


def _package_node_id(github_repository_id: int, package_name: str) -> str:
    return repository_scoped_key(github_repository_id, "package", package_name)


def _endpoint_node_id(github_repository_id: int, http_method: str, path: str) -> str:
    return repository_scoped_key(github_repository_id, "endpoint", f"{http_method}:{path}")


# ---------- 노드 생성 ----------


def _build_package_node(github_repository_id: int, package_name: str) -> GraphNode:
    return GraphNode(
        id=_package_node_id(github_repository_id, package_name),
        type="Package",
        properties={"name": package_name, "githubRepositoryId": github_repository_id},
    )


def _build_class_node(
    class_id: str,
    class_result: ClassResultProtocol,
    qualified_name: str,
    file_path: str,
    github_repository_id: int,
    language: str,
) -> GraphNode:
    node_type = "Interface" if class_result.kind == "interface" else "Class"
    return GraphNode(
        id=class_id,
        type=node_type,
        properties={
            "name": class_result.name,
            "qualified_name": qualified_name,
            "layer": class_result.layer,
            "path": file_path,
            "githubRepositoryId": github_repository_id,
            "language": language,
            # Neo4j properties cannot contain maps; keep field metadata as a
            # primitive string array that can be stored and queried directly.
            "fields": [f"{field.type} {field.name}" for field in class_result.fields],
        },
    )


def _build_method_node(
    method_id: str,
    method_result: MethodResultProtocol,
    class_result: ClassResultProtocol,
    class_qualified_name: str,
    github_repository_id: int,
    language: str,
) -> GraphNode:
    properties: dict = {
        "name": method_result.name,
        "signature": method_result.param_signature,
        "is_constructor": method_result.is_constructor,
        # CALLS 해석 시 "이 메서드가 어느 클래스 소속인지" 역참조하는 용도
        "class_name": class_result.name,
        "class_qualified_name": class_qualified_name,
        "githubRepositoryId": github_repository_id,
        "language": language,
    }
    if method_result.api_mapping:
        properties["http_method"] = method_result.api_mapping.http_method
        properties["path"] = method_result.api_mapping.path
    return GraphNode(id=method_id, type="Method", properties=properties)


def _build_method_version_node(
    version_id: str,
    method_id: str,
    method_result: MethodResultProtocol,
    github_repository_id: int,
    content_hash: str,
    language: str,
) -> GraphNode:
    properties: dict = {
        "methodKey": method_id,
        "contentHash": content_hash,
        "sourceCode": method_result.text,
        "startLine": method_result.start_line,
        "endLine": method_result.end_line,
        "githubRepositoryId": github_repository_id,
        # CALLS 엣지의 source가 Method가 아니라 MethodVersion 노드이기 때문에
        # (아래 _map_file_document의 HAS_VERSION/CALLS 배선 참고), 언어 스코핑을
        # 하려면 이 노드도 자기 언어를 알아야 함 — 없으면 resolve_cross_file_
        # references가 모든 CALLS 엣지를 "java" 기본값으로 잘못 취급하게 됨.
        "language": language,
    }
    if method_result.api_mapping:
        properties["httpMethod"] = method_result.api_mapping.http_method
        properties["apiPath"] = method_result.api_mapping.path
    return GraphNode(id=version_id, type="MethodVersion", properties=properties)


def _build_endpoint_node(github_repository_id: int, http_method: str, path: str) -> GraphNode:
    return GraphNode(
        id=_endpoint_node_id(github_repository_id, http_method, path),
        type="Endpoint",
        properties={
            "http_method": http_method,
            "path": path,
            "githubRepositoryId": github_repository_id,
        },
    )


# ---------- 엣지 생성 ----------


def _build_contains_edge(source_id: str, target_id: str) -> GraphEdge:
    return GraphEdge(type="CONTAINS", source=source_id, target=target_id, properties={})


def _build_imports_edges(class_id: str, imports: tuple[str, ...]) -> list[GraphEdge]:
    return [
        GraphEdge(type="IMPORTS", source=class_id, target=name, properties={"resolved": False})
        for name in imports
    ]


def _build_extends_edge(class_id: str, class_result: ClassResultProtocol) -> GraphEdge | None:
    if not class_result.extends:
        return None
    return GraphEdge(
        type="EXTENDS",
        source=class_id,
        target=class_result.extends,
        properties={"resolved": False, "generic_params": class_result.extends_generic_params},
    )


def _build_implements_edges(class_id: str, class_result: ClassResultProtocol) -> list[GraphEdge]:
    return [
        GraphEdge(type="IMPLEMENTS", source=class_id, target=name, properties={"resolved": False})
        for name in class_result.implements
    ]


def _build_manages_edge(class_id: str, class_result: ClassResultProtocol) -> GraphEdge | None:
    """Repository 계층 클래스가 다루는 Entity 추론 (예: JpaRepository<Poll, Long> -> Poll)."""
    if class_result.layer != "Repository" or not class_result.extends_generic_params:
        return None
    entity_name = class_result.extends_generic_params[0]
    return GraphEdge(
        type="MANAGES", source=class_id, target=entity_name, properties={"resolved": False}
    )


def _resolve_receiver_type(receiver: str | None, class_result: ClassResultProtocol) -> str | None:
    """호출 리시버 식별자를 (아는 한도 내에서) 타입 이름으로 바꿔줌.

    리시버가 없으면(`foo()`) 같은 클래스 메서드 호출로 가정하고 자기 자신의
    클래스 이름을 돌려줌. 리시버가 필드 이름이면 그 필드의 선언 타입을
    돌려줌. 지역 변수 등 필드가 아닌 경우엔 타입을 알 방법이 없어서 None.
    """
    if receiver is None:
        return class_result.name
    for field in class_result.fields:
        if field.name == receiver:
            return field.type
    return None


def _build_calls_edges(
    method_id: str, method_result: MethodResultProtocol, class_result: ClassResultProtocol
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for call in method_result.invoked_calls:
        properties: dict = {"resolved": False}
        receiver_type = _resolve_receiver_type(call.receiver, class_result)
        if receiver_type:
            properties["receiver_type"] = receiver_type
        edges.append(
            GraphEdge(type="CALLS", source=method_id, target=call.name, properties=properties)
        )
    return edges


def _build_exposes_edge(method_id: str, endpoint_id: str) -> GraphEdge:
    return GraphEdge(type="EXPOSES", source=method_id, target=endpoint_id, properties={})


# ---------- 1단계: 파일 하나 변환 ----------
#
# 언어별 진입점(map_java_file/map_javascript_file)은 전부 아래 _map_file_document
# 하나로 위임함 — 로직은 완전히 언어 무관(파일 하나 -> 노드/엣지 변환 규칙 자체가
# Java 전용이 아니라, 이미 검증된 것을 언어별로 복제하는 대신 재사용하는 것).
# 실제로 언어마다 달라지는 부분은 전부 파서(app/parsers/languages/*.py)가 이미
# FileResultProtocol 모양으로 정규화해서 내보내기 때문에 여기서는 분기가 필요 없음.


def _map_file_document(
    github_repository_id: int,
    file_result: FileResultProtocol,
    commit_hash: str,
    *,
    language: str,
) -> GraphDocument:
    """파일 하나(어떤 언어든)의 파싱 결과를 GraphDocument(노드+엣지)로 변환.

    CALLS/EXTENDS/IMPLEMENTS/IMPORTS/MANAGES 엣지는 아직 미해결
    (target이 실제 노드 id가 아니라 이름 문자열) 상태로 나옴 — 프로젝트의
    모든 파일을 이 함수로 변환한 다음 resolve_cross_file_references()에
    전부 넘겨야 최종 그래프가 완성됨. Class/Method 노드에는 language
    property가 붙어서, 이름이 우연히 겹치는 다른 언어의 심볼과 섞여서
    resolve되지 않도록 함(resolve_cross_file_references 참고).
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    normalized_path = normalize_repository_path(file_result.path)
    source_file_id = file_key(github_repository_id, normalized_path)
    nodes.append(
        GraphNode(
            id=source_file_id,
            type="File",
            properties={
                "path": normalized_path,
                "githubRepositoryId": github_repository_id,
            },
        )
    )
    commit_id = repository_scoped_key(github_repository_id, "commit", commit_hash)
    nodes.append(
        GraphNode(
            id=commit_id,
            type="Commit",
            properties={"sha": commit_hash, "githubRepositoryId": github_repository_id},
        )
    )

    package_id: str | None = None
    if file_result.package:
        package_id = _package_node_id(github_repository_id, file_result.package)
        nodes.append(_build_package_node(github_repository_id, file_result.package))

    for class_result in file_result.classes:
        node_type = "Interface" if class_result.kind == "interface" else "Class"
        if not class_result.name:
            raise ValueError(f"Unnamed {language} declaration in {normalized_path}.")
        qualified_name = class_result.qualified_name or java_qualified_name(
            file_result.package, (), class_result.name
        )
        class_id = class_key(
            github_repository_id, normalized_path, node_type, qualified_name
        )
        nodes.append(
            _build_class_node(
                class_id,
                class_result,
                qualified_name,
                normalized_path,
                github_repository_id,
                language,
            )
        )
        edges.append(
            GraphEdge(
                type="DECLARES",
                source=source_file_id,
                target=class_id,
                properties={},
            )
        )

        if package_id:
            edges.append(_build_contains_edge(package_id, class_id))

        edges.extend(_build_imports_edges(class_id, file_result.imports))

        extends_edge = _build_extends_edge(class_id, class_result)
        if extends_edge:
            edges.append(extends_edge)
        edges.extend(_build_implements_edges(class_id, class_result))

        manages_edge = _build_manages_edge(class_id, class_result)
        if manages_edge:
            edges.append(manages_edge)

        for method_result in class_result.methods:
            if not method_result.name:
                raise ValueError(f"Unnamed {language} method in {qualified_name}.")
            if method_result.is_constructor:
                method_id = constructor_key(
                    class_id, class_result.name, method_result.param_signature
                )
            else:
                method_id = method_key(
                    class_id, method_result.name, method_result.param_signature
                )
            nodes.append(
                _build_method_node(
                    method_id,
                    method_result,
                    class_result,
                    qualified_name,
                    github_repository_id,
                    language,
                )
            )
            edges.append(_build_contains_edge(class_id, method_id))
            content_hash = method_content_hash(method_result.text)
            version_id = method_version_key(method_id, content_hash)
            nodes.append(
                _build_method_version_node(
                    version_id,
                    method_id,
                    method_result,
                    github_repository_id,
                    content_hash,
                    language,
                )
            )
            edges.append(
                GraphEdge(type="HAS_VERSION", source=method_id, target=version_id, properties={})
            )
            edges.append(
                GraphEdge(
                    type="INTRODUCED_IN",
                    source=version_id,
                    target=commit_id,
                    properties={},
                )
            )
            edges.extend(_build_calls_edges(version_id, method_result, class_result))

            if method_result.api_mapping:
                http_method = method_result.api_mapping.http_method
                path = method_result.api_mapping.path
                nodes.append(_build_endpoint_node(github_repository_id, http_method, path))
                edges.append(
                    _build_exposes_edge(
                        method_id,
                        _endpoint_node_id(github_repository_id, http_method, path),
                    )
                )

    return GraphDocument(nodes=tuple(nodes), edges=tuple(edges))


def map_java_file(
    github_repository_id: int,
    file_result: JavaFileResult,
    commit_hash: str,
) -> GraphDocument:
    """자바 파일 파싱 결과 하나를 GraphDocument(노드+엣지)로 변환.

    실제 변환 로직은 _map_file_document()에 위임(language="java") — 동작은
    이 함수가 분리돼 있던 이전과 완전히 동일함.
    """
    return _map_file_document(github_repository_id, file_result, commit_hash, language="java")


def map_javascript_file(
    github_repository_id: int,
    file_result: JavaScriptFileResult,
    commit_hash: str,
) -> GraphDocument:
    """JS/JSX 파일 파싱 결과 하나를 GraphDocument(노드+엣지)로 변환.

    map_java_file과 동일하게 _map_file_document()에 위임(language="javascript").
    file_result.package가 항상 None이라 package 노드/CONTAINS 엣지는 안 생기고,
    나머지(File/Class/Method/CALLS 등)는 Java와 동일한 규칙으로 만들어짐.
    """
    return _map_file_document(
        github_repository_id, file_result, commit_hash, language="javascript"
    )


def map_typescript_file(
    github_repository_id: int,
    file_result: TypeScriptFileResult,
    commit_hash: str,
) -> GraphDocument:
    """TS/TSX 파일 파싱 결과 하나를 GraphDocument(노드+엣지)로 변환.

    map_javascript_file과 동일하게 _map_file_document()에 위임
    (language="typescript") — Class/Interface/Method 노드 생성, EXTENDS/
    IMPLEMENTS/CALLS 엣지 배선 규칙 전부 동일하게 적용됨.
    """
    return _map_file_document(
        github_repository_id, file_result, commit_hash, language="typescript"
    )


def map_python_file(
    github_repository_id: int,
    file_result: PythonFileResult,
    commit_hash: str,
) -> GraphDocument:
    """Python 파일 파싱 결과 하나를 GraphDocument(노드+엣지)로 변환.

    map_java_file/map_javascript_file과 동일하게 _map_file_document()에
    위임(language="python"). file_result.package가 항상 None이라 package
    노드/CONTAINS 엣지는 안 생김.
    """
    return _map_file_document(github_repository_id, file_result, commit_hash, language="python")


# ---------- 2단계: 여러 파일 합치고 이름 해석 ----------


def resolve_cross_file_references(documents: Iterable[GraphDocument]) -> GraphDocument:
    """여러 GraphDocument를 하나로 합치고, 미해결(resolved=False) 엣지의
    target을 실제 노드 id로 연결 시도함.

    CALLS는 메서드 이름 인덱스로, EXTENDS/IMPLEMENTS/MANAGES는 클래스 이름
    인덱스로, IMPORTS는 import 문자열의 마지막 조각(단순 클래스명)을 클래스
    이름 인덱스로 찾아봄. 후보가 여럿이면 전부 연결하고 ambiguous=True,
    후보가 없으면 target을 원래 이름 그대로 두고 external=True로 표시함.

    인덱스 키는 (language, name) 튜플임 — 여러 언어가 섞인 프로젝트에서
    Java `save()`와 Python/JS `save()`가 이름만 같다는 이유로 잘못 이어지는
    걸 막기 위함. edge의 source 노드가 속한 언어로만 후보를 찾고, 같은
    언어에 후보가 없으면 다른 언어로 재시도하지 않고 곧장 external=True로
    떨어짐(의도적 — 언어 경계를 넘는 이름 매칭은 대부분 우연의 일치일 뿐임).
    """
    all_nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []
    for document in documents:
        all_nodes.extend(document.nodes)
        all_edges.extend(document.edges)

    methods_by_name: dict[tuple[str, str], list[str]] = {}
    classes_by_name: dict[tuple[str, str], list[str]] = {}
    classes_by_fqn: dict[tuple[str, str], list[str]] = {}
    method_class_names: dict[str, set[str]] = {}
    node_language: dict[str, str] = {}
    for node in all_nodes:
        name = node.properties.get("name")
        language = node.properties.get("language", "java")
        if node.type in ("Method", "MethodVersion", "Class", "Interface"):
            # MethodVersion 포함: CALLS 엣지의 source는 Method가 아니라
            # MethodVersion 노드 id라서(HAS_VERSION 배선), 여기 빠지면
            # edge_language 조회가 항상 기본값 "java"로 폴백해버림.
            node_language[node.id] = language
        if node.type == "Method":
            class_names = {
                value
                for value in (
                    node.properties.get("class_name"),
                    node.properties.get("class_qualified_name"),
                )
                if value
            }
            method_class_names[node.id] = class_names
        if not name:
            continue
        if node.type == "Method":
            methods_by_name.setdefault((language, name), []).append(node.id)
        elif node.type in ("Class", "Interface"):
            classes_by_name.setdefault((language, name), []).append(node.id)
            qualified_name = node.properties.get("qualified_name")
            if qualified_name:
                classes_by_fqn.setdefault((language, qualified_name), []).append(node.id)

    resolved_edges: list[GraphEdge] = []
    for edge in all_edges:
        if edge.properties.get("resolved") is not False:
            resolved_edges.append(edge)
            continue

        # edge.source(호출/상속하는 쪽)의 언어로만 후보를 찾음 — source가
        # Method/Class가 아닌 경우는 현재 미해결 엣지 타입(CALLS/EXTENDS/
        # IMPLEMENTS/IMPORTS/MANAGES) 중엔 없으므로 항상 찾김. 못 찾으면
        # (이론상 발생 안 함) "java" 기본값으로 안전하게 폴백.
        edge_language = node_language.get(edge.source, "java")

        if edge.type == "CALLS":
            candidates = methods_by_name.get((edge_language, edge.target), [])
            # 리시버 타입을 알면(필드 타입 매칭 등) 그 타입 소속 메서드로 후보를 좁힘.
            # 좁혔더니 하나도 안 남으면(타입을 잘못 짚었거나 상속받은 메서드 등)
            # 원래 후보 목록으로 되돌아감 — 안 좁히는 것보다는 넓게라도 남기는 게 나음.
            receiver_type = edge.properties.get("receiver_type")
            if receiver_type and candidates:
                narrowed = [
                    cid for cid in candidates if receiver_type in method_class_names.get(cid, set())
                ]
                if narrowed:
                    candidates = narrowed
        elif edge.type == "IMPORTS":
            simple_name = edge.target.rsplit(".", 1)[-1]
            candidates = classes_by_fqn.get(
                (edge_language, edge.target), []
            ) or classes_by_name.get((edge_language, simple_name), [])
        else:  # EXTENDS / IMPLEMENTS / MANAGES
            candidates = classes_by_fqn.get(
                (edge_language, edge.target), []
            ) or classes_by_name.get((edge_language, edge.target), [])

        if not candidates:
            resolved_edges.append(
                GraphEdge(
                    type=edge.type,
                    source=edge.source,
                    target=edge.target,
                    properties={**edge.properties, "external": True},
                )
            )
        elif len(candidates) == 1:
            resolved_edges.append(
                GraphEdge(
                    type=edge.type,
                    source=edge.source,
                    target=candidates[0],
                    properties={**edge.properties, "resolved": True},
                )
            )
        else:
            for candidate_id in candidates:
                resolved_edges.append(
                    GraphEdge(
                        type=edge.type,
                        source=edge.source,
                        target=candidate_id,
                        properties={**edge.properties, "resolved": True, "ambiguous": True},
                    )
                )

    unique_nodes = {node.id: node for node in all_nodes}
    return GraphDocument(nodes=tuple(unique_nodes.values()), edges=tuple(resolved_edges))
