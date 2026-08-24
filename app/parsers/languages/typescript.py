"""TypeScript/TSX 전용 Tree-sitter 추출 로직.

app/parsers/languages/javascript.py와 거의 동일한 패턴이지만(호출/리시버
추출 로직은 사실상 동일한 문법 노드를 공유해서 그대로 재사용), TS 고유
문법 때문에 클래스/필드/상속 쪽 처리가 좀 더 풍부함:

- 클래스 상속이 `class_heritage` 안에 `extends_clause`/`implements_clause`로
  분리되어 나옴(JS는 `implements` 자체가 없음).
- `extends Base<T>`처럼 제네릭 상속이 가능해서, Java의 JpaRepository<Entity>
  패턴과 동일하게 extends_generic_params를 채워서 MANAGES 엣지 추론에 씀.
- 필드 선언(`public_field_definition`)에 타입 주석이 있어서, JS/Python처럼
  타입을 추측할 필요 없이 실제 타입을 그대로 씀 — 리시버 타입 매칭 정확도가
  JS/Python보다 높음.
- `interface` 문법이 실제로 있어서 kind="interface"로 구분함(단, 인터페이스
  멤버는 본문이 없는 시그니처라 methods는 항상 빈 튜플로 둠 — CALLS 그래프에
  실질적으로 기여할 게 없어서).

`.ts`/`.tsx`는 별도 grammar 두 개(tree-sitter-typescript 패키지가 각각
제공)라 파일 확장자로 골라 씀 — .ts는 JSX 문법을 파싱 못 해서 반드시
구분해야 함.
"""

import re

import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node

from app.dtos.analysis import (
    FieldResult,
    HttpCall,
    MethodCall,
    TypeScriptClassResult,
    TypeScriptFileResult,
    TypeScriptMethodResult,
)
from app.graph.identifiers import normalize_java_parameter_signature
from app.parsers.tree_sitter import (
    build_parser,
    find_nodes_by_type,
    get_child_by_field,
    get_node_text,
    parse_source,
)

TYPESCRIPT_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())

_CLASS_TYPES = {"class_declaration"}
_INTERFACE_TYPES = {"interface_declaration"}
_TOP_LEVEL_FUNCTION_VALUE_TYPES = {"arrow_function", "function_expression"}
_FIELD_TYPES = {"public_field_definition", "field_definition"}

_MODULE_CLASS_SUFFIX = "$module"
_HTTP_METHODS = "get|post|put|patch|delete|head|options"
_HTTP_CALL_PATTERN = re.compile(
    rf"(?:axios|http|api)\.({_HTTP_METHODS})\(\s*['\"](?P<path>[^'\"`]+)['\"]",
    re.IGNORECASE,
)
_FETCH_CALL_PATTERN = re.compile(
    r"fetch\(\s*['\"](?P<path>[^'\"`]+)['\"](?P<options>[^)]*)\)", re.IGNORECASE
)

_PATH_KEYWORD_LAYERS: tuple[tuple[str, str], ...] = (
    ("hooks/", "Hook"),
    ("services/", "Service"),
    ("service/", "Service"),
    ("api/", "Service"),
    ("store/", "Store"),
    ("reducers/", "Store"),
    ("utils/", "Util"),
    ("util/", "Util"),
)


def parse_typescript_file(path: str, source_bytes: bytes) -> TypeScriptFileResult:
    """TS/TSX 소스 파일 하나를 파싱해서 import/클래스+인터페이스(+합성 module
    클래스) 목록을 반환함. `.tsx`면 JSX를 파싱할 수 있는 grammar를, 그 외
    (`.ts`)면 순수 TS grammar를 씀.
    """
    language = TSX_LANGUAGE if path.endswith(".tsx") else TYPESCRIPT_LANGUAGE
    parser = build_parser(language)
    tree = parse_source(parser, source_bytes)
    root_node = tree.root_node

    imports = extract_imports(root_node, source_bytes)

    classes = [
        _build_class_result(node, source_bytes, path)
        for node in find_nodes_by_type(root_node, _CLASS_TYPES)
    ]
    classes.extend(
        _build_interface_result(node, source_bytes, path)
        for node in find_nodes_by_type(root_node, _INTERFACE_TYPES)
    )

    module_class = _build_module_class_result(root_node, source_bytes, path)
    if module_class is not None:
        classes.append(module_class)

    return TypeScriptFileResult(
        path=path,
        package=None,
        imports=tuple(imports),
        classes=tuple(classes),
    )


# ---------- 파일 레벨 ----------


def extract_imports(root_node: Node, source_bytes: bytes) -> list[str]:
    """`import ... from '모듈경로'`의 모듈경로 문자열만 뽑음 (JS 파서와 동일)."""
    imports: list[str] = []
    for import_node in find_nodes_by_type(root_node, "import_statement"):
        source_node = get_child_by_field(import_node, "source")
        if source_node is None:
            continue
        raw = get_node_text(source_node, source_bytes)
        imports.append(raw.strip("'\"`"))
    return imports


# ---------- 클래스/인터페이스 레벨 ----------


def _strip_generic_args(text: str) -> str:
    """`BaseRepository<User, number>` -> `BaseRepository`처럼 제네릭 인자를
    베이스 이름에서 떼어냄 (별도로 extends_generic_params에 보존함).
    """
    return text.split("<", 1)[0]


def _extract_generic_args(text: str) -> tuple[str, ...]:
    """`BaseRepository<User, number>`에서 `("User", "number")`를 뽑음.
    제네릭이 없으면 빈 튜플.
    """
    if "<" not in text or not text.endswith(">"):
        return ()
    inner = text[text.index("<") + 1 : -1]
    return tuple(part.strip() for part in inner.split(",") if part.strip())


def _extract_class_heritage(
    class_node: Node, source_bytes: bytes
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """class_heritage에서 (extends, extends_generic_params, implements)를 뽑음."""
    heritage = next(
        (child for child in class_node.children if child.type == "class_heritage"), None
    )
    if heritage is None:
        return None, (), ()

    extends: str | None = None
    extends_generic_params: tuple[str, ...] = ()
    extends_clause = next(
        (child for child in heritage.children if child.type == "extends_clause"), None
    )
    if extends_clause is not None:
        # extends_clause 노드 전체 텍스트를 씀(예: "extends BaseRepository<User, number>").
        # target 노드(베이스 식별자/member_expression) 하나만 골라서 텍스트를 뽑으면
        # 그 옆의 type_arguments("<User, number>")가 통째로 빠져버려서
        # extends_generic_params가 항상 빈 튜플이 되는 버그가 있었음 — 반드시
        # extends_clause 전체에서 "extends" 키워드만 떼어내는 방식으로 처리해야 함.
        full_text = get_node_text(extends_clause, source_bytes).strip()
        if full_text.startswith("extends"):
            full_text = full_text[len("extends") :].strip()
        if full_text:
            extends = _strip_generic_args(full_text)
            extends_generic_params = _extract_generic_args(full_text)

    implements: list[str] = []
    implements_clause = next(
        (child for child in heritage.children if child.type == "implements_clause"), None
    )
    if implements_clause is not None:
        for child in implements_clause.children:
            if child.type in ("implements", ","):
                continue
            implements.append(_strip_generic_args(get_node_text(child, source_bytes)))

    return extends, extends_generic_params, tuple(implements)


def _classify_layer(class_name: str | None, file_path: str) -> str:
    lower_path = file_path.lower()
    for keyword, layer in _PATH_KEYWORD_LAYERS:
        if keyword in lower_path:
            return layer
    if class_name and class_name[:1].isupper():
        return "Component"
    return "Module"


def _build_class_result(node: Node, source_bytes: bytes, file_path: str) -> TypeScriptClassResult:
    name_node = get_child_by_field(node, "name")
    class_name = get_node_text(name_node, source_bytes) if name_node else None
    extends, extends_generic_params, implements = _extract_class_heritage(node, source_bytes)
    layer = _classify_layer(class_name, file_path)

    body_node = get_child_by_field(node, "body")
    method_nodes = (
        [child for child in body_node.children if child.type == "method_definition"]
        if body_node is not None
        else []
    )
    methods = tuple(_method_result_from_node(member, source_bytes) for member in method_nodes)
    fields = _extract_field_definitions(body_node, source_bytes) if body_node is not None else []

    return TypeScriptClassResult(
        name=class_name,
        kind="class",
        layer=layer,
        extends=extends,
        extends_generic_params=extends_generic_params,
        implements=implements,
        fields=tuple(fields),
        methods=methods,
        qualified_name=class_name,
    )


def _build_interface_result(
    node: Node, source_bytes: bytes, file_path: str
) -> TypeScriptClassResult:
    """interface_declaration을 클래스와 같은 그래프 형태로 변환.

    인터페이스 멤버(property_signature/method_signature)는 본문이 없는
    시그니처라 실행 가능한 코드가 아님 — methods는 항상 빈 튜플로 둠
    (CALLS 그래프에 실질적으로 기여할 게 없어서). EXTENDS/구조 파악
    (누가 이 인터페이스를 구현/상속하는지)에는 여전히 유용함.
    """
    name_node = get_child_by_field(node, "name")
    interface_name = get_node_text(name_node, source_bytes) if name_node else None
    layer = _classify_layer(interface_name, file_path)

    extends: str | None = None
    implements: list[str] = []
    heritage = next(
        (child for child in node.children if child.type == "extends_type_clause"), None
    )
    if heritage is not None:
        type_children = [
            child for child in heritage.children if child.type not in ("extends", ",")
        ]
        if type_children:
            extends = _strip_generic_args(get_node_text(type_children[0], source_bytes))
            implements = [
                _strip_generic_args(get_node_text(child, source_bytes))
                for child in type_children[1:]
            ]

    return TypeScriptClassResult(
        name=interface_name,
        kind="interface",
        layer=layer,
        extends=extends,
        extends_generic_params=(),
        implements=tuple(implements),
        fields=(),
        methods=(),
        qualified_name=interface_name,
    )


def _extract_field_definitions(body_node: Node, source_bytes: bytes) -> list[FieldResult]:
    """클래스 필드를 타입 주석에서 그대로 뽑음.

    TS는 타입 주석이 흔해서(`private repo: PollRepository;`), JS/Python처럼
    생성자 호출로 타입을 추측할 필요가 거의 없음 — 있으면 그대로 쓰고,
    없으면(타입 주석 생략 + 초기값도 없는 경우) 건너뜀.
    """
    fields: list[FieldResult] = []
    for child in body_node.children:
        if child.type not in _FIELD_TYPES:
            continue
        name_node = get_child_by_field(child, "name")
        type_node = get_child_by_field(child, "type")
        if name_node is None or type_node is None:
            continue
        # type_annotation 노드는 [":", <실제 타입>] 모양이라 ":" 다음 것만 씀
        type_inner = next((c for c in type_node.children if c.type != ":"), None)
        if type_inner is None:
            continue
        fields.append(
            FieldResult(
                name=get_node_text(name_node, source_bytes),
                type=get_node_text(type_inner, source_bytes),
            )
        )
    return fields


# ---------- 합성 module 클래스 (최상위 orphan 함수) ----------


def _module_class_name(file_path: str) -> str:
    stem = file_path.rsplit("/", 1)[-1]
    for suffix in (".tsx", ".ts"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return f"{stem}{_MODULE_CLASS_SUFFIX}"


def _unwrap_export(node: Node) -> Node:
    if node.type == "export_statement":
        declaration = get_child_by_field(node, "declaration")
        if declaration is not None:
            return declaration
    return node


def _build_module_class_result(
    root_node: Node, source_bytes: bytes, file_path: str
) -> TypeScriptClassResult | None:
    methods: list[TypeScriptMethodResult] = []

    for child in root_node.children:
        declaration = _unwrap_export(child)

        if declaration.type == "function_declaration":
            methods.append(_method_result_from_node(declaration, source_bytes))
            continue

        if declaration.type in ("lexical_declaration", "variable_declaration"):
            for declarator in declaration.children:
                if declarator.type != "variable_declarator":
                    continue
                value_node = get_child_by_field(declarator, "value")
                if value_node is None or value_node.type not in _TOP_LEVEL_FUNCTION_VALUE_TYPES:
                    continue
                name_node = get_child_by_field(declarator, "name")
                name = get_node_text(name_node, source_bytes) if name_node else None
                methods.append(
                    _method_result_from_node(
                        value_node, source_bytes, name_override=name, span_node=declarator
                    )
                )

    if not methods:
        return None

    module_name = _module_class_name(file_path)
    return TypeScriptClassResult(
        name=module_name,
        kind="class",
        layer=_classify_layer(None, file_path),
        extends=None,
        extends_generic_params=(),
        implements=(),
        fields=(),
        methods=tuple(methods),
        qualified_name=module_name,
    )


# ---------- 메서드/함수 레벨 (클래스 메서드 + 최상위 함수 공용) ----------
#
# 호출/리시버 추출 로직은 JS와 완전히 같은 문법 노드(call_expression/
# member_expression)를 씀 — javascript.py의 로직을 그대로 복제함(모듈
# 재사용은 안 함, 두 언어의 파서가 서로 독립적으로 유지되게 하려는 의도적
# 선택 — Java/JS/Python도 같은 이유로 서로 복제하는 패턴을 씀).


def _get_param_signature(node: Node, source_bytes: bytes) -> str:
    params_node = get_child_by_field(node, "parameters")
    if params_node is None:
        return "()"
    return normalize_java_parameter_signature(get_node_text(params_node, source_bytes))


def _extract_receiver(call_node: Node, source_bytes: bytes) -> str | None:
    function_node = get_child_by_field(call_node, "function")
    if function_node is None or function_node.type != "member_expression":
        return None

    object_node = get_child_by_field(function_node, "object")
    if object_node is None:
        return None
    if object_node.type == "identifier":
        return get_node_text(object_node, source_bytes)
    if object_node.type == "this":
        return None
    if object_node.type == "member_expression":
        inner_object = get_child_by_field(object_node, "object")
        inner_property = get_child_by_field(object_node, "property")
        if inner_object is not None and inner_object.type == "this" and inner_property is not None:
            return get_node_text(inner_property, source_bytes)
    return None


def _extract_invoked_names(body_node: Node, source_bytes: bytes) -> list[MethodCall]:
    calls: list[MethodCall] = []
    for call_node in find_nodes_by_type(body_node, "call_expression"):
        function_node = get_child_by_field(call_node, "function")
        if function_node is None:
            continue
        if function_node.type == "identifier":
            calls.append(MethodCall(receiver=None, name=get_node_text(function_node, source_bytes)))
        elif function_node.type == "member_expression":
            property_node = get_child_by_field(function_node, "property")
            if property_node is None:
                continue
            receiver = _extract_receiver(call_node, source_bytes)
            calls.append(
                MethodCall(receiver=receiver, name=get_node_text(property_node, source_bytes))
            )
    return calls


def _extract_http_calls(body_node: Node, source_bytes: bytes) -> list[HttpCall]:
    source = get_node_text(body_node, source_bytes)
    calls = [
        HttpCall(http_method=match.group(1).upper(), path=match.group("path"))
        for match in _HTTP_CALL_PATTERN.finditer(source)
    ]
    for match in _FETCH_CALL_PATTERN.finditer(source):
        method_match = re.search(
            r"method\s*:\s*['\"](?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)['\"]",
            match.group("options"),
            re.IGNORECASE,
        )
        calls.append(
            HttpCall(
                http_method=method_match.group("method").upper() if method_match else "GET",
                path=match.group("path"),
            )
        )
    return calls


def _method_result_from_node(
    node: Node,
    source_bytes: bytes,
    *,
    name_override: str | None = None,
    span_node: Node | None = None,
) -> TypeScriptMethodResult:
    is_constructor = False
    name = name_override
    if name is None:
        name_node = get_child_by_field(node, "name")
        if name_node is not None:
            name = get_node_text(name_node, source_bytes)
            is_constructor = name == "constructor" and node.type == "method_definition"

    range_node = span_node if span_node is not None else node
    param_signature = _get_param_signature(node, source_bytes)

    body_node = get_child_by_field(node, "body")
    invoked_calls = _extract_invoked_names(body_node, source_bytes) if body_node is not None else []
    http_calls = _extract_http_calls(body_node, source_bytes) if body_node is not None else []

    return TypeScriptMethodResult(
        name=name,
        param_signature=param_signature,
        is_constructor=is_constructor,
        start_line=range_node.start_point[0] + 1,
        end_line=range_node.end_point[0] + 1,
        text=get_node_text(range_node, source_bytes),
        api_mapping=None,
        invoked_calls=tuple(invoked_calls),
        http_calls=tuple(http_calls),
    )
