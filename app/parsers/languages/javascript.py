"""JavaScript/JSX 전용 Tree-sitter 추출 로직.

app/parsers/languages/java.py와 같은 패턴 — app/parsers/tree_sitter.py의 범용
유틸에 의존하고, 여기서는 JS 전용 판단만 담당함. Java 파서와의 핵심 구조적
차이 하나: **Java는 모든 메서드가 클래스 안에 있지만, JS는 최상위(top-level)
함수/화살표 함수가 흔함**(모듈 함수, React 함수형 컴포넌트, 훅). 이런 orphan
함수들을 그래프 스키마 변경 없이 담기 위해, 파일마다 필요할 때만 합성
"module" 클래스(`kind="class"`, `layer="Module"`)를 하나 만들어서 그 안에
넣는다 — app/services/chunking.py의 "메서드는 클래스에 속한다"는 가정도
그대로 유지됨.

CALLS 관계는 이름(+가능하면 리시버)만 뽑아서 반환하고, 실제로 어느 함수를
가리키는지 해석은 여러 파일을 다 모은 뒤 app/graph/mappings.py의 2차 패스에서
처리함(Java와 동일).
"""

import re

import tree_sitter_javascript as tsjavascript
from tree_sitter import Language, Node

from app.dtos.analysis import (
    FieldResult,
    HttpCall,
    JavaScriptClassResult,
    JavaScriptFileResult,
    JavaScriptMethodResult,
    MethodCall,
)
from app.graph.identifiers import normalize_java_parameter_signature
from app.parsers.tree_sitter import (
    build_parser,
    find_nodes_by_type,
    get_child_by_field,
    get_node_text,
    parse_source,
)

JAVASCRIPT_LANGUAGE = Language(tsjavascript.language())

_CLASS_TYPES = {"class_declaration"}
_TOP_LEVEL_FUNCTION_VALUE_TYPES = {"arrow_function", "function_expression"}

# 최상위 orphan 함수를 담는 합성 클래스 이름 접미사. 실제 클래스와 겹치지
# 않도록 파일 안에서 절대 안 쓰일 접미사를 붙임.
_MODULE_CLASS_SUFFIX = "$module"
_HTTP_METHODS = "get|post|put|patch|delete|head|options"
_HTTP_CALL_PATTERN = re.compile(
    rf"(?:axios|http|api)\.({ _HTTP_METHODS })\(\s*['\"](?P<path>[^'\"`]+)['\"]",
    re.IGNORECASE,
)
_FETCH_CALL_PATTERN = re.compile(
    r"fetch\(\s*['\"](?P<path>[^'\"`]+)['\"](?P<options>[^)]*)\)", re.IGNORECASE
)

# React 컴포넌트/훅 관례에 기반한 최선-노력(best-effort) 레이어 분류.
# Java의 classify_layer만큼 정교하지 않음 — 이름 규칙 + 경로 키워드만 봄.
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


def parse_javascript_file(path: str, source_bytes: bytes) -> JavaScriptFileResult:
    """JS/JSX 소스 파일 하나를 파싱해서 import/클래스(+합성 module 클래스)
    목록을 반환함. 파일 하나만 보고 판단 가능한 정보까지만 담음.
    """
    parser = build_parser(JAVASCRIPT_LANGUAGE)
    tree = parse_source(parser, source_bytes)
    root_node = tree.root_node

    imports = extract_imports(root_node, source_bytes)

    class_nodes = find_nodes_by_type(root_node, _CLASS_TYPES)
    classes = [_build_class_result(node, source_bytes, path) for node in class_nodes]

    module_class = _build_module_class_result(root_node, source_bytes, path)
    if module_class is not None:
        classes.append(module_class)

    return JavaScriptFileResult(
        path=path,
        package=None,  # JS 모듈은 파일 경로 기반이라 Java식 패키지 개념 없음
        imports=tuple(imports),
        classes=tuple(classes),
    )


# ---------- 파일 레벨 ----------


def extract_imports(root_node: Node, source_bytes: bytes) -> list[str]:
    """`import ... from '모듈경로'`의 모듈경로 문자열만 뽑음.

    대부분 npm 패키지명(예: "react") 또는 상대경로(예: "../services")라
    그래프 해석 단계에서 external=True로 남는 게 정상 — Java의 JDK import와
    같은 취급.
    """
    imports: list[str] = []
    for import_node in find_nodes_by_type(root_node, "import_statement"):
        source_node = get_child_by_field(import_node, "source")
        if source_node is None:
            continue
        raw = get_node_text(source_node, source_bytes)
        imports.append(raw.strip("'\"`"))
    return imports


# ---------- 클래스 레벨 ----------


def _extract_superclass(class_node: Node, source_bytes: bytes) -> str | None:
    """`class Foo extends Bar.Baz {}`에서 "Bar.Baz" 텍스트를 뽑음.

    tree-sitter-javascript는 class_declaration에 "superclass" 필드를 안 주고
    class_heritage 서브노드로 감싸서 준다 — extends 키워드가 아닌 나머지
    자식(identifier 또는 member_expression)의 텍스트를 그대로 씀.
    """
    heritage = next(
        (child for child in class_node.children if child.type == "class_heritage"), None
    )
    if heritage is None:
        return None
    target = next((child for child in heritage.children if child.type != "extends"), None)
    if target is None:
        return None
    return get_node_text(target, source_bytes)


def _classify_layer(class_name: str | None, file_path: str) -> str:
    """Java의 classify_layer만큼 정교하진 않은 best-effort 휴리스틱.

    PascalCase 이름은 React 컴포넌트로 흔히 쓰이지만 신뢰도가 낮아서
    "Component"로 단정하지 않고, 경로 키워드 우선 -> 그 외 "Module".
    """
    lower_path = file_path.lower()
    for keyword, layer in _PATH_KEYWORD_LAYERS:
        if keyword in lower_path:
            return layer
    if class_name and class_name[:1].isupper():
        return "Component"
    return "Module"


def _build_class_result(node: Node, source_bytes: bytes, file_path: str) -> JavaScriptClassResult:
    name_node = get_child_by_field(node, "name")
    class_name = get_node_text(name_node, source_bytes) if name_node else None
    superclass = _extract_superclass(node, source_bytes)
    layer = _classify_layer(class_name, file_path)

    body_node = get_child_by_field(node, "body")
    method_nodes = (
        [child for child in body_node.children if child.type == "method_definition"]
        if body_node is not None
        else []
    )
    methods = tuple(
        _method_result_from_node(member, source_bytes) for member in method_nodes
    )
    fields = _extract_field_definitions(body_node, source_bytes) if body_node is not None else []

    return JavaScriptClassResult(
        name=class_name,
        kind="class",  # JS에는 interface 키워드가 없음
        layer=layer,
        extends=superclass,
        extends_generic_params=(),  # JS에 해당 개념 없음
        implements=(),  # JS에 해당 개념 없음
        fields=tuple(fields),
        methods=methods,
        qualified_name=class_name,  # JS는 패키지가 없어서 파일 내 이름 그대로
    )


def _extract_field_definitions(body_node: Node, source_bytes: bytes) -> list[FieldResult]:
    """클래스 필드(`this.foo`가 아니라 `field = value;` 선언 형태)를 뽑음.

    JS는 필드에 타입이 없어서 type은 항상 빈 문자열 — Java처럼 리시버 타입을
    필드 타입과 매칭해서 CALLS를 좁히는 용도로는 못 쓰지만, 필드 이름 자체는
    남겨서 향후 확장 여지를 둠.
    """
    fields: list[FieldResult] = []
    for child in body_node.children:
        if child.type != "field_definition":
            continue
        name_node = get_child_by_field(child, "property")
        if name_node is not None:
            fields.append(FieldResult(name=get_node_text(name_node, source_bytes), type=""))
    return fields


# ---------- 합성 module 클래스 (최상위 orphan 함수) ----------


def _module_class_name(file_path: str) -> str:
    stem = file_path.rsplit("/", 1)[-1]
    for suffix in (".jsx", ".js"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return f"{stem}{_MODULE_CLASS_SUFFIX}"


def _unwrap_export(node: Node) -> Node:
    """`export function foo() {}` 같은 export_statement 안의 실제 선언을 꺼냄."""
    if node.type == "export_statement":
        declaration = get_child_by_field(node, "declaration")
        if declaration is not None:
            return declaration
    return node


def _build_module_class_result(
    root_node: Node, source_bytes: bytes, file_path: str
) -> JavaScriptClassResult | None:
    methods: list[JavaScriptMethodResult] = []

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
    return JavaScriptClassResult(
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


def _get_param_signature(node: Node, source_bytes: bytes) -> str:
    """파라미터 목록 텍스트를 정규화해서 시그니처 문자열로 씀.

    JS엔 정적 타입이 없어서 Java처럼 "타입만" 뽑을 수 없음 — 대신 파라미터
    목록 원문(기본값/구조분해/rest 포함)을 그대로 정규화해서 오버로드 유사
    상황(같은 이름, 다른 시그니처)을 구분하는 용도로 씀.
    normalize_java_parameter_signature는 이름과 달리 공백 제거 + 괄호 검증만
    하는 언어 무관 함수라 여기서도 그대로 재사용함.
    """
    params_node = get_child_by_field(node, "parameters")
    if params_node is None:
        return "()"
    return normalize_java_parameter_signature(get_node_text(params_node, source_bytes))


def _extract_receiver(call_node: Node, source_bytes: bytes) -> str | None:
    """call_expression에서 리시버 식별자를 뽑음 (Java의 _extract_receiver와 대응).

    `pollService.castVote(...)` -> "pollService"
    `this.onVote(...)` (한 단계) -> None (같은 클래스/모듈 함수 호출로 취급)
    `this.foo.bar(...)` (두 단계, this.필드.메서드) -> "foo"
    `foo(...)` (리시버 없음) -> None
    체이닝(`list.map(...).filter(...)`)처럼 object가 다시 call_expression인
    경우는 Java의 체이닝 처리와 동일하게 None으로 남김.
    """
    function_node = get_child_by_field(call_node, "function")
    if function_node is None or function_node.type != "member_expression":
        return None  # bare identifier() 호출 -> 리시버 없음

    object_node = get_child_by_field(function_node, "object")
    if object_node is None:
        return None
    if object_node.type == "identifier":
        return get_node_text(object_node, source_bytes)
    if object_node.type == "this":
        return None  # this.method() -> 같은 클래스 인스턴스 메서드 호출
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
) -> JavaScriptMethodResult:
    """method_definition/function_declaration/arrow_function/function_expression
    노드 하나를 공용 JavaScriptMethodResult로 변환.

    화살표 함수(`const foo = () => {...}`)는 이름이 노드 자체가 아니라 감싸는
    variable_declarator에 있어서 name_override로 넘겨받음. span_node가 있으면
    start_line/end_line/text는 (화살표 함수 본체가 아니라) 대입문 전체를
    기준으로 계산해서 `const foo = ...` 선언부까지 포함시킴.
    """
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

    return JavaScriptMethodResult(
        name=name,
        param_signature=param_signature,
        is_constructor=is_constructor,
        start_line=range_node.start_point[0] + 1,
        end_line=range_node.end_point[0] + 1,
        text=get_node_text(range_node, source_bytes),
        api_mapping=None,  # Express 라우트 매핑은 이번 범위에서 제외 (플랜 참고)
        invoked_calls=tuple(invoked_calls),
        http_calls=tuple(http_calls),
    )
