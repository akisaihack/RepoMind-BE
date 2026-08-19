"""자바 전용 Tree-sitter 추출 로직 (Spring 컨벤션 포함).

app/parsers/tree_sitter.py의 범용 유틸(트리 순회, 텍스트 추출 등)에 의존하고,
여기서는 "이게 Controller인지 Service인지", "이 메서드가 어떤 API 경로에
매핑되는지" 같은 자바/Spring 전용 판단만 담당함.

CALLS 관계(메서드 호출 이름)는 이름만 뽑아서 반환하고, 실제로 어느 메서드를
가리키는지 해석(이름 매칭)하는 건 여러 파일을 다 모은 뒤에나 가능하므로
app/graph/mappings.py의 2차 패스에서 처리함.
"""

import re

import tree_sitter_java as tsjava
from tree_sitter import Language, Node

from app.dtos.analysis import (
    APIMapping,
    ExtendsImplementsResult,
    FieldResult,
    JavaClassResult,
    JavaFileResult,
    JavaMethodResult,
    MethodCall,
)
from app.graph.identifiers import java_qualified_name, normalize_java_parameter_signature
from app.parsers.tree_sitter import (
    build_parser,
    find_nodes_by_type,
    get_child_by_field,
    get_node_text,
    parse_source,
    walk,
)

JAVA_LANGUAGE = Language(tsjava.language())

_CLASS_LIKE_TYPES = {"class_declaration", "interface_declaration"}
_MEMBER_TYPES = {"method_declaration", "constructor_declaration"}

# --- 레이어 판별 기준 (우선순위: 어노테이션 > 상속/구현 > 이름 규칙 > 패키지 경로) ---

_ANNOTATION_LAYERS: dict[str, str] = {
    "@RestController": "Controller",
    "@Controller": "Controller",
    "@Service": "Service",
    "@Repository": "Repository",
    "@Configuration": "Config",
    "@Aspect": "Aspect",
    "@EventListener": "EventListener",
    "@Entity": "Entity",
}

_INHERITANCE_LAYERS: dict[str, str] = {
    "JpaRepository": "Repository",
    "CrudRepository": "Repository",
    "PagingAndSortingRepository": "Repository",
    "OncePerRequestFilter": "Filter",
    "Filter": "Filter",
    "HandlerInterceptor": "Interceptor",
    "ApplicationListener": "EventListener",
    "Exception": "Exception",
    "RuntimeException": "Exception",
}

_NAME_SUFFIX_LAYERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("Controller",), "Controller"),
    (("Service", "ServiceImpl"), "Service"),
    (("Repository", "Dao", "Mapper"), "Repository"),
    (("DTO", "Dto", "Request", "Response", "VO", "Payload", "Form"), "DTO"),
    (("Util", "Utils", "Helper"), "Util"),
    (("Client",), "Client"),
    (("Config",), "Config"),
    (("Filter",), "Filter"),
    (("Interceptor",), "Interceptor"),
    (("Listener",), "EventListener"),
    (("Exception",), "Exception"),
)

_PACKAGE_KEYWORD_LAYERS: tuple[tuple[str, str], ...] = (
    ("util", "Util"),
    ("common", "Util"),
    ("config", "Config"),
    ("exception", "Exception"),
    ("dto", "DTO"),
    ("payload", "DTO"),
    ("request", "DTO"),
    ("response", "DTO"),
)

_API_ANNOTATIONS: dict[str, str] = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "REQUEST",
}

# `@GetMapping` 같은 축약형 어노테이션은 Spring 4.3부터 생겨서, 그 이전
# 스타일로 짜인 코드는 `@RequestMapping(method = RequestMethod.GET, ...)`
# 처럼 명시적으로 HTTP 메서드를 지정하는 경우가 흔함. 이 패턴을 못 잡으면
# 전부 "REQUEST"(메서드 불명)로만 표시돼서 따로 감지함.
_REQUEST_METHOD_PATTERN = re.compile(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)")


def parse_java_file(path: str, source_bytes: bytes) -> JavaFileResult:
    """자바 소스 파일 하나를 파싱해서 패키지/import/클래스 목록을 반환함.

    파일 하나만 보고 판단 가능한 정보까지만 담고, CALLS 해석처럼 다른
    파일과 대조해야 하는 건 여기서 하지 않음.
    """
    parser = build_parser(JAVA_LANGUAGE)
    tree = parse_source(parser, source_bytes)
    root_node = tree.root_node

    package = extract_package(root_node, source_bytes)
    imports = extract_imports(root_node, source_bytes)

    class_nodes = find_nodes_by_type(root_node, _CLASS_LIKE_TYPES)
    classes = tuple(
        _build_class_result(node, source_bytes, path, package) for node in class_nodes
    )

    return JavaFileResult(
        path=path,
        package=package,
        imports=tuple(imports),
        classes=classes,
    )


# ---------- 파일 레벨 ----------

def extract_package(root_node: Node, source_bytes: bytes) -> str | None:
    """파일 최상단의 package 선언에서 패키지명을 뽑음."""
    for child in root_node.children:
        if child.type == "package_declaration":
            text = get_node_text(child, source_bytes)
            return text.replace("package", "", 1).replace(";", "").strip()
    return None


def extract_imports(root_node: Node, source_bytes: bytes) -> list[str]:
    """파일의 import 선언들을 원본 그대로(FQN 문자열) 뽑음.

    와일드카드(`import foo.bar.*;`) 필터링 여부는 이 함수의 책임이 아니라
    이 결과를 쓰는 그래프 매핑 단계에서 결정함.
    """
    imports: list[str] = []
    for child in root_node.children:
        if child.type == "import_declaration":
            text = get_node_text(child, source_bytes)
            name = text.replace("import", "", 1).replace("static", "", 1).replace(";", "").strip()
            imports.append(name)
    return imports


# ---------- 클래스/인터페이스 레벨 ----------

def get_declaration_header(node: Node, source_bytes: bytes) -> str:
    """클래스/메서드 선언에서 본문(body) 앞부분(어노테이션+선언부)만 반환.

    layer 판별, extends/implements 추출, API 경로 추출이 전부 이 헤더
    텍스트를 기준으로 정규식 매칭을 함.

    본문 시작 위치는 텍스트에서 첫 "{"를 찾는 방식이 아니라 실제 트리의
    "body" 필드 위치를 씀. 텍스트 검색 방식은 `@RequestMapping(value=
    {"/a","/b"})`나 `@SuppressWarnings({"unchecked"})`처럼 어노테이션
    안에 "{"가 들어있으면 거기서 잘못 잘리는 문제가 있었음.
    """
    body_node = get_child_by_field(node, "body")
    if body_node is not None:
        return source_bytes[node.start_byte:body_node.start_byte].decode("utf-8")
    return get_node_text(node, source_bytes)


def classify_layer(
    header_text: str,
    class_name: str | None,
    file_path: str,
    extends_result: ExtendsImplementsResult,
) -> str:
    """클래스가 어떤 레이어(Controller/Service/Repository 등)인지 판별.

    검사 순서: 어노테이션 -> 상속·구현 대상 -> 클래스 이름 규칙 -> 패키지
    경로. 먼저 매칭되는 걸로 확정하고, 끝까지 안 걸리면 "Other".
    """
    for annotation, layer in _ANNOTATION_LAYERS.items():
        if annotation in header_text:
            return layer

    inheritance_targets = [extends_result.extends_name, *extends_result.implements_names]
    for target in inheritance_targets:
        if target and target in _INHERITANCE_LAYERS:
            return _INHERITANCE_LAYERS[target]

    if class_name:
        for suffixes, layer in _NAME_SUFFIX_LAYERS:
            if class_name.endswith(suffixes):
                return layer

    lower_path = file_path.lower()
    for keyword, layer in _PACKAGE_KEYWORD_LAYERS:
        if keyword in lower_path:
            return layer

    return "Other"


def extract_extends_implements(header_text: str) -> ExtendsImplementsResult:
    """extends/implements 대상을 이름 기반 정규식으로 추출.

    extends 대상의 제네릭 타입 파라미터는 버리지 않고 따로 보존함
    (예: `JpaRepository<Poll, Long>` -> extends_name="JpaRepository",
    extends_generic_params=("Poll", "Long")). 완벽한 타입 해석은 아니고
    이름 매칭 기반이라는 한계가 있음.
    """
    extends_match = re.search(r"\bextends\s+([\w<>,.\s]+?)(?=\s+implements\b|$)", header_text)
    implements_match = re.search(r"\bimplements\s+([\w<>,.\s]+)$", header_text)

    extends_name: str | None = None
    extends_generic_params: list[str] = []
    implements_names: list[str] = []

    if extends_match:
        raw = extends_match.group(1).strip()
        generic_match = re.search(r"<(.+)>", raw)
        if generic_match:
            extends_generic_params = [
                part.strip() for part in generic_match.group(1).split(",") if part.strip()
            ]
        extends_name = re.sub(r"<.*?>", "", raw).split(",")[0].strip()

    if implements_match:
        raw = implements_match.group(1).strip()
        for part in raw.split(","):
            name = re.sub(r"<.*?>", "", part).strip()
            if name:
                implements_names.append(name)

    return ExtendsImplementsResult(
        extends_name=extends_name,
        extends_generic_params=tuple(extends_generic_params),
        implements_names=tuple(implements_names),
    )


def extract_fields(class_node: Node, source_bytes: bytes) -> list[FieldResult]:
    """클래스 직속 필드들의 이름+타입 목록 (중첩 클래스의 필드는 제외).

    두 군데서 씀: `@Autowired` 필드처럼 의존성 주입 파악(DEPENDS_ON 관계)
    재료, 그리고 메서드 호출의 리시버 이름을 필드 타입과 매칭해서 CALLS를
    좁히는 재료(app/graph/mappings.py).

    필드 하나에 변수가 여러 개 선언된 경우(`int a, b;`)도 각각 따로 담음.
    """
    fields: list[FieldResult] = []

    def _visit(node: Node) -> bool | None:
        if node.type in _CLASS_LIKE_TYPES:
            return True  # 중첩 클래스 안으로는 들어가지 않음
        if node.type == "field_declaration":
            type_node = get_child_by_field(node, "type")
            if not type_node:
                return None
            type_text = re.sub(r"<.*?>", "", get_node_text(type_node, source_bytes)).strip()
            for declarator in node.children:
                if declarator.type != "variable_declarator":
                    continue
                name_node = get_child_by_field(declarator, "name")
                if name_node:
                    fields.append(
                        FieldResult(name=get_node_text(name_node, source_bytes), type=type_text)
                    )
        return None

    for child in _class_body_children(class_node):
        walk(child, _visit)

    return fields


def _class_body_children(class_node: Node) -> list[Node]:
    body_node = get_child_by_field(class_node, "body")
    return list(body_node.children) if body_node else []


def _direct_class_members(class_node: Node, member_types: set[str]) -> list[Node]:
    """중첩 클래스는 건너뛰고, 이 클래스 바로 아래(직속) 멤버 노드만 모음."""
    members: list[Node] = []

    def _visit(node: Node) -> bool | None:
        if node.type in _CLASS_LIKE_TYPES:
            return True  # 중첩 클래스는 스킵 (그 안의 메서드는 별도 클래스 항목으로 처리됨)
        if node.type in member_types:
            members.append(node)
        return None

    for child in _class_body_children(class_node):
        walk(child, _visit)

    return members


def _enclosing_class_names(class_node: Node, source_bytes: bytes) -> tuple[str, ...]:
    names: list[str] = []
    parent = class_node.parent
    while parent is not None:
        if parent.type in _CLASS_LIKE_TYPES:
            name_node = get_child_by_field(parent, "name")
            if name_node is not None:
                names.append(get_node_text(name_node, source_bytes))
        parent = parent.parent
    names.reverse()
    return tuple(names)


def _build_class_result(
    class_node: Node,
    source_bytes: bytes,
    file_path: str,
    package_name: str | None,
) -> JavaClassResult:
    name_node = get_child_by_field(class_node, "name")
    class_name = get_node_text(name_node, source_bytes) if name_node else None
    header_text = get_declaration_header(class_node, source_bytes)
    kind = "interface" if class_node.type == "interface_declaration" else "class"

    extends_result = extract_extends_implements(header_text)
    layer = classify_layer(header_text, class_name, file_path, extends_result)
    fields = extract_fields(class_node, source_bytes)

    # 클래스 레벨 @RequestMapping이 있으면 메서드 경로 앞에 붙는 base path로 씀
    class_mapping = extract_api_mapping(class_node, source_bytes)
    base_path = class_mapping.path if class_mapping else ""

    member_nodes = _direct_class_members(class_node, _MEMBER_TYPES)
    methods = tuple(
        _build_method_result(member_node, source_bytes, base_path) for member_node in member_nodes
    )

    qualified_name = (
        java_qualified_name(
            package_name,
            _enclosing_class_names(class_node, source_bytes),
            class_name,
        )
        if class_name
        else None
    )

    return JavaClassResult(
        name=class_name,
        kind=kind,
        layer=layer,
        extends=extends_result.extends_name,
        extends_generic_params=extends_result.extends_generic_params,
        implements=extends_result.implements_names,
        fields=tuple(fields),
        methods=methods,
        qualified_name=qualified_name,
    )


# ---------- 메서드/생성자 레벨 ----------

def get_param_signature(node: Node, source_bytes: bytes) -> str:
    """파라미터 타입들로 시그니처 문자열을 만듦 (오버로딩 구분용 ID 재료).

    예: `save(Order order, boolean force)` -> "(Order,boolean)"
    """
    params_node = get_child_by_field(node, "parameters")
    if params_node is None:
        return "()"
    types: list[str] = []
    for child in params_node.children:
        if child.type in {"formal_parameter", "spread_parameter"}:
            type_node = get_child_by_field(child, "type")
            if type_node is None and child.type == "spread_parameter":
                type_node = next(
                    (
                        candidate
                        for candidate in child.named_children
                        if candidate.type != "variable_declarator"
                    ),
                    None,
                )
            if type_node:
                type_text = get_node_text(type_node, source_bytes)
                if child.type == "spread_parameter":
                    type_text += "..."
                types.append(type_text)
    return normalize_java_parameter_signature("(" + ",".join(types) + ")")


def extract_api_mapping(node: Node, source_bytes: bytes) -> APIMapping | None:
    """`@GetMapping("/path")` 같은 매핑 어노테이션에서 HTTP 메서드+경로를 추출.

    클래스 노드에도, 메서드 노드에도 똑같이 쓸 수 있음 (클래스 레벨
    `@RequestMapping`으로 base path를 뽑을 때도 이 함수를 재사용함).
    경로 값이 없는 축약형(`@GetMapping`만 있고 괄호 없음)도 처리함.
    """
    header_text = get_declaration_header(node, source_bytes)

    for annotation, http_method in _API_ANNOTATIONS.items():
        match = re.search(
            rf'@{annotation}\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']', header_text
        )
        if match:
            if annotation == "RequestMapping":
                method_match = _REQUEST_METHOD_PATTERN.search(header_text)
                if method_match:
                    http_method = method_match.group(1)
            return APIMapping(http_method=http_method, path=match.group(1))
        if re.search(rf"@{annotation}\b(?!\w)", header_text):
            return APIMapping(http_method=http_method, path="")

    return None


def _extract_receiver(invocation_node: Node, source_bytes: bytes) -> str | None:
    """method_invocation 노드에서 리시버(호출 대상) 식별자를 뽑음.

    `pollRepository.findById(...)` -> "pollRepository"
    `this.pollRepository.findById(...)` -> "pollRepository" (this. 는 무시)
    `foo(...)` (리시버 없음) -> None
    `list.stream().filter(...)` 처럼 리시버가 단순 식별자가 아니면 -> None
    (체이닝까지 해석하려면 타입 추론이 필요해서 범위 밖으로 둠)
    """
    object_node = get_child_by_field(invocation_node, "object")
    if object_node is None:
        return None
    if object_node.type == "identifier":
        return get_node_text(object_node, source_bytes)
    if object_node.type == "field_access":
        field_object = get_child_by_field(object_node, "object")
        field_name_node = get_child_by_field(object_node, "field")
        if field_object is not None and field_object.type == "this" and field_name_node is not None:
            return get_node_text(field_name_node, source_bytes)
    return None


def extract_invoked_names(method_body_node: Node, source_bytes: bytes) -> list[MethodCall]:
    """메서드 본문 안에서 호출되는 메서드들을 전부 찾음 (리시버 + 이름, 타입 추론 X).

    실제로 어느 클래스의 어느 메서드를 가리키는지 최종 해석하는 건
    app/graph/mappings.py의 몫 — 여기선 리시버 식별자까지만 뽑아줌.
    """
    invocation_nodes = find_nodes_by_type(method_body_node, "method_invocation")
    calls: list[MethodCall] = []
    for node in invocation_nodes:
        name_node = get_child_by_field(node, "name")
        if name_node:
            receiver = _extract_receiver(node, source_bytes)
            calls.append(MethodCall(receiver=receiver, name=get_node_text(name_node, source_bytes)))
    return calls


def _build_method_result(
    method_node: Node, source_bytes: bytes, base_path: str
) -> JavaMethodResult:
    is_constructor = method_node.type == "constructor_declaration"
    name_node = get_child_by_field(method_node, "name")
    name = get_node_text(name_node, source_bytes) if name_node else None
    param_signature = get_param_signature(method_node, source_bytes)

    api_mapping = None
    if not is_constructor:
        method_mapping = extract_api_mapping(method_node, source_bytes)
        if method_mapping:
            full_path = (base_path.rstrip("/") + "/" + method_mapping.path.lstrip("/")).rstrip("/")
            api_mapping = APIMapping(http_method=method_mapping.http_method, path=full_path)

    body_node = get_child_by_field(method_node, "body")
    invoked_calls = extract_invoked_names(body_node, source_bytes) if body_node else []

    return JavaMethodResult(
        name=name,
        param_signature=param_signature,
        is_constructor=is_constructor,
        start_line=method_node.start_point[0] + 1,
        end_line=method_node.end_point[0] + 1,
        text=get_node_text(method_node, source_bytes),
        api_mapping=api_mapping,
        invoked_calls=tuple(invoked_calls),
    )
