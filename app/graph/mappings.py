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

from app.dtos.analysis import JavaClassResult, JavaFileResult, JavaMethodResult
from app.dtos.graph import GraphDocument, GraphEdge, GraphNode

# ---------- 노드 ID 생성 ----------
#
# 이름 기반(예: 패키지+클래스명) 대신 "파일 안에서 몇 번째 클래스/메서드인지"
# 인덱스 기반으로 id를 만듦. 같은 파일 안에 이름이 겹치는 중첩 클래스가 있어도
# (드물지만) 항상 유일한 id가 나오기 때문. Package/Endpoint id만 이름 기반인데,
# 이건 의도적임 — 같은 패키지/엔드포인트가 여러 파일에 걸쳐 나올 때 자동으로
# 같은 노드로 합쳐지길 원해서(Neo4j MERGE 기준 키 역할).


def _package_node_id(package_name: str) -> str:
    return f"Package::{package_name}"


def _class_node_id(file_path: str, class_index: int) -> str:
    return f"Class::{file_path}::{class_index}"


def _method_node_id(class_id: str, method_index: int) -> str:
    return f"Method::{class_id}::{method_index}"


def _endpoint_node_id(http_method: str, path: str) -> str:
    return f"Endpoint::{http_method}::{path}"


# ---------- 노드 생성 ----------


def _build_package_node(package_name: str) -> GraphNode:
    return GraphNode(
        id=_package_node_id(package_name),
        type="Package",
        properties={"name": package_name},
    )


def _build_class_node(class_id: str, class_result: JavaClassResult, file_path: str) -> GraphNode:
    node_type = "Interface" if class_result.kind == "interface" else "Class"
    return GraphNode(
        id=class_id,
        type=node_type,
        properties={
            "name": class_result.name,
            "layer": class_result.layer,
            "path": file_path,
            "fields": [
                {"name": field.name, "type": field.type} for field in class_result.fields
            ],
        },
    )


def _build_method_node(
    method_id: str, method_result: JavaMethodResult, class_result: JavaClassResult
) -> GraphNode:
    properties: dict = {
        "name": method_result.name,
        "signature": method_result.param_signature,
        "is_constructor": method_result.is_constructor,
        "start_line": method_result.start_line,
        "end_line": method_result.end_line,
        # CALLS 해석 시 "이 메서드가 어느 클래스 소속인지" 역참조하는 용도
        "class_name": class_result.name,
    }
    if method_result.api_mapping:
        properties["http_method"] = method_result.api_mapping.http_method
        properties["path"] = method_result.api_mapping.path
    return GraphNode(id=method_id, type="Method", properties=properties)


def _build_endpoint_node(http_method: str, path: str) -> GraphNode:
    return GraphNode(
        id=_endpoint_node_id(http_method, path),
        type="Endpoint",
        properties={"http_method": http_method, "path": path},
    )


# ---------- 엣지 생성 ----------


def _build_contains_edge(source_id: str, target_id: str) -> GraphEdge:
    return GraphEdge(type="CONTAINS", source=source_id, target=target_id, properties={})


def _build_imports_edges(class_id: str, imports: tuple[str, ...]) -> list[GraphEdge]:
    return [
        GraphEdge(type="IMPORTS", source=class_id, target=name, properties={"resolved": False})
        for name in imports
    ]


def _build_extends_edge(class_id: str, class_result: JavaClassResult) -> GraphEdge | None:
    if not class_result.extends:
        return None
    return GraphEdge(
        type="EXTENDS",
        source=class_id,
        target=class_result.extends,
        properties={"resolved": False, "generic_params": class_result.extends_generic_params},
    )


def _build_implements_edges(class_id: str, class_result: JavaClassResult) -> list[GraphEdge]:
    return [
        GraphEdge(type="IMPLEMENTS", source=class_id, target=name, properties={"resolved": False})
        for name in class_result.implements
    ]


def _build_manages_edge(class_id: str, class_result: JavaClassResult) -> GraphEdge | None:
    """Repository 계층 클래스가 다루는 Entity 추론 (예: JpaRepository<Poll, Long> -> Poll)."""
    if class_result.layer != "Repository" or not class_result.extends_generic_params:
        return None
    entity_name = class_result.extends_generic_params[0]
    return GraphEdge(
        type="MANAGES", source=class_id, target=entity_name, properties={"resolved": False}
    )


def _resolve_receiver_type(receiver: str | None, class_result: JavaClassResult) -> str | None:
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
    method_id: str, method_result: JavaMethodResult, class_result: JavaClassResult
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for call in method_result.invoked_calls:
        properties: dict = {"resolved": False}
        receiver_type = _resolve_receiver_type(call.receiver, class_result)
        if receiver_type:
            properties["receiver_type"] = receiver_type
        edges.append(GraphEdge(type="CALLS", source=method_id, target=call.name, properties=properties))
    return edges


def _build_exposes_edge(method_id: str, endpoint_id: str) -> GraphEdge:
    return GraphEdge(type="EXPOSES", source=method_id, target=endpoint_id, properties={})


# ---------- 1단계: 파일 하나 변환 ----------


def map_java_file(file_result: JavaFileResult) -> GraphDocument:
    """자바 파일 파싱 결과 하나를 GraphDocument(노드+엣지)로 변환.

    CALLS/EXTENDS/IMPLEMENTS/IMPORTS/MANAGES 엣지는 아직 미해결
    (target이 실제 노드 id가 아니라 이름 문자열) 상태로 나옴 — 프로젝트의
    모든 파일을 이 함수로 변환한 다음 resolve_cross_file_references()에
    전부 넘겨야 최종 그래프가 완성됨.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    package_id: str | None = None
    if file_result.package:
        package_id = _package_node_id(file_result.package)
        nodes.append(_build_package_node(file_result.package))

    for class_index, class_result in enumerate(file_result.classes):
        class_id = _class_node_id(file_result.path, class_index)
        nodes.append(_build_class_node(class_id, class_result, file_result.path))

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

        for method_index, method_result in enumerate(class_result.methods):
            method_id = _method_node_id(class_id, method_index)
            nodes.append(_build_method_node(method_id, method_result, class_result))
            edges.append(_build_contains_edge(class_id, method_id))
            edges.extend(_build_calls_edges(method_id, method_result, class_result))

            if method_result.api_mapping:
                http_method = method_result.api_mapping.http_method
                path = method_result.api_mapping.path
                nodes.append(_build_endpoint_node(http_method, path))
                edges.append(_build_exposes_edge(method_id, _endpoint_node_id(http_method, path)))

    return GraphDocument(nodes=tuple(nodes), edges=tuple(edges))


# ---------- 2단계: 여러 파일 합치고 이름 해석 ----------


def resolve_cross_file_references(documents: Iterable[GraphDocument]) -> GraphDocument:
    """여러 GraphDocument를 하나로 합치고, 미해결(resolved=False) 엣지의
    target을 실제 노드 id로 연결 시도함.

    CALLS는 메서드 이름 인덱스로, EXTENDS/IMPLEMENTS/MANAGES는 클래스 이름
    인덱스로, IMPORTS는 import 문자열의 마지막 조각(단순 클래스명)을 클래스
    이름 인덱스로 찾아봄. 후보가 여럿이면 전부 연결하고 ambiguous=True,
    후보가 없으면 target을 원래 이름 그대로 두고 external=True로 표시함.
    """
    all_nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []
    for document in documents:
        all_nodes.extend(document.nodes)
        all_edges.extend(document.edges)

    method_index: dict[str, list[str]] = {}
    class_index: dict[str, list[str]] = {}
    method_class_name: dict[str, str] = {}
    for node in all_nodes:
        name = node.properties.get("name")
        if node.type == "Method":
            class_name = node.properties.get("class_name")
            if class_name:
                method_class_name[node.id] = class_name
        if not name:
            continue
        if node.type == "Method":
            method_index.setdefault(name, []).append(node.id)
        elif node.type in ("Class", "Interface"):
            class_index.setdefault(name, []).append(node.id)

    resolved_edges: list[GraphEdge] = []
    for edge in all_edges:
        if edge.properties.get("resolved") is not False:
            resolved_edges.append(edge)
            continue

        if edge.type == "CALLS":
            candidates = method_index.get(edge.target, [])
            # 리시버 타입을 알면(필드 타입 매칭 등) 그 타입 소속 메서드로 후보를 좁힘.
            # 좁혔더니 하나도 안 남으면(타입을 잘못 짚었거나 상속받은 메서드 등)
            # 원래 후보 목록으로 되돌아감 — 안 좁히는 것보다는 넓게라도 남기는 게 나음.
            receiver_type = edge.properties.get("receiver_type")
            if receiver_type and candidates:
                narrowed = [cid for cid in candidates if method_class_name.get(cid) == receiver_type]
                if narrowed:
                    candidates = narrowed
        elif edge.type == "IMPORTS":
            simple_name = edge.target.rsplit(".", 1)[-1]
            candidates = class_index.get(simple_name, [])
        else:  # EXTENDS / IMPLEMENTS / MANAGES
            candidates = class_index.get(edge.target, [])

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

    return GraphDocument(nodes=tuple(all_nodes), edges=tuple(resolved_edges))
