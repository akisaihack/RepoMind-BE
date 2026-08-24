"""Python 전용 Tree-sitter 추출 로직.

app/parsers/languages/javascript.py와 거의 같은 패턴 — 클래스 메서드뿐 아니라
클래스 밖 최상위 함수(모듈 함수)도 흔한 언어라서, JS와 마찬가지로 파일당
합성 "module" 클래스(`{stem}$module`)를 만들어 orphan 함수를 담는다.

JS/Java와 다른 Python 고유 처리 두 가지:
1. **데코레이터**: `@app.route(...)`, `@staticmethod` 등이 함수/클래스 선언을
   `decorated_definition` 노드로 한 겹 감싸서 내보냄 — `_unwrap_decorated()`로
   실제 function_definition/class_definition을 꺼내야 함.
2. **생성자 판별**: Java/JS처럼 문법적으로 구분되는 생성자가 없고, 이름이
   `__init__`인 메서드를 관례상 생성자로 취급함.
"""

import tree_sitter_python as tspython
from tree_sitter import Language, Node

from app.dtos.analysis import (
    FieldResult,
    MethodCall,
    PythonClassResult,
    PythonFileResult,
    PythonMethodResult,
)
from app.graph.identifiers import normalize_java_parameter_signature
from app.parsers.tree_sitter import (
    build_parser,
    find_nodes_by_type,
    get_child_by_field,
    get_node_text,
    parse_source,
)

PYTHON_LANGUAGE = Language(tspython.language())

_CLASS_TYPES = {"class_definition"}
_CONSTRUCTOR_NAME = "__init__"

# 최상위 orphan 함수를 담는 합성 클래스 이름 접미사 (JS 파서와 동일한 규칙).
_MODULE_CLASS_SUFFIX = "$module"

# 흔한 Python 백엔드 디렉터리 관례에 기반한 best-effort 레이어 분류.
# Java의 classify_layer만큼 정교하지 않음 — 경로 키워드 + 이름 규칙만 봄.
_PATH_KEYWORD_LAYERS: tuple[tuple[str, str], ...] = (
    ("repository/", "Repository"),
    ("repositories/", "Repository"),
    ("service/", "Service"),
    ("services/", "Service"),
    ("controller/", "Controller"),
    ("controllers/", "Controller"),
    ("api/", "Service"),
    ("model/", "Entity"),
    ("models/", "Entity"),
    ("util/", "Util"),
    ("utils/", "Util"),
)


def parse_python_file(path: str, source_bytes: bytes) -> PythonFileResult:
    """Python 소스 파일 하나를 파싱해서 import/클래스(+합성 module 클래스)
    목록을 반환함. 파일 하나만 보고 판단 가능한 정보까지만 담음.
    """
    parser = build_parser(PYTHON_LANGUAGE)
    tree = parse_source(parser, source_bytes)
    root_node = tree.root_node

    imports = extract_imports(root_node, source_bytes)

    class_nodes = find_nodes_by_type(root_node, _CLASS_TYPES)
    classes = [_build_class_result(node, source_bytes, path) for node in class_nodes]

    module_class = _build_module_class_result(root_node, source_bytes, path)
    if module_class is not None:
        classes.append(module_class)

    return PythonFileResult(
        path=path,
        package=None,  # Python 패키지는 디렉터리(__init__.py) 기반 — 파일 하나만 봐선 모름
        imports=tuple(imports),
        classes=tuple(classes),
    )


def _unwrap_decorated(node: Node) -> Node:
    """데코레이터가 감싼 decorated_definition에서 실제 function_definition/
    class_definition을 꺼냄. 데코레이터가 없으면 node를 그대로 돌려줌.
    """
    if node.type == "decorated_definition":
        definition = get_child_by_field(node, "definition")
        if definition is not None:
            return definition
    return node


def _function_name(node: Node, source_bytes: bytes) -> str | None:
    name_node = get_child_by_field(node, "name")
    return get_node_text(name_node, source_bytes) if name_node else None


# ---------- 파일 레벨 ----------


def extract_imports(root_node: Node, source_bytes: bytes) -> list[str]:
    """`import a.b`/`from a.b import C`의 모듈 경로 문자열만 뽑음.

    상대 임포트(`from . import x`)나 표준 라이브러리 대부분은 그래프 해석
    단계에서 external=True로 남는 게 정상 — Java의 JDK import와 같은 취급.
    """
    imports: list[str] = []
    for node in find_nodes_by_type(root_node, {"import_statement", "import_from_statement"}):
        if node.type == "import_from_statement":
            module_node = get_child_by_field(node, "module_name")
            if module_node is not None:
                imports.append(get_node_text(module_node, source_bytes))
        else:
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    imports.append(get_node_text(child, source_bytes))
    return imports


# ---------- 클래스 레벨 ----------


def _extract_bases(class_node: Node, source_bytes: bytes) -> list[str]:
    """`class Foo(Base, Mixin, metaclass=X):`에서 위치 인자로 온 베이스
    이름들만 뽑음 (keyword_argument로 오는 `metaclass=X` 등은 상속 관계가
    아니라서 제외).
    """
    superclasses_node = get_child_by_field(class_node, "superclasses")
    if superclasses_node is None:
        return []
    return [
        get_node_text(child, source_bytes)
        for child in superclasses_node.children
        if child.type in ("identifier", "attribute")
    ]


def _classify_layer(class_name: str | None, file_path: str) -> str:
    """Java의 classify_layer만큼 정교하진 않은 best-effort 휴리스틱."""
    lower_path = file_path.lower()
    for keyword, layer in _PATH_KEYWORD_LAYERS:
        if keyword in lower_path:
            return layer
    if class_name and class_name[:1].isupper():
        return "Component"
    return "Module"


def _build_class_result(node: Node, source_bytes: bytes, file_path: str) -> PythonClassResult:
    name_node = get_child_by_field(node, "name")
    class_name = get_node_text(name_node, source_bytes) if name_node else None
    bases = _extract_bases(node, source_bytes)
    # 첫 번째 베이스만 extends로, 다중 상속의 나머지는 implements 자리에 재사용
    # (Java의 "인터페이스 구현"과 정확히 같은 의미는 아니지만, "추가로 상속하는
    # 것들"이라는 의미로 그래프 스키마를 그대로 씀 — IMPLEMENTS 엣지 생성됨).
    extends = bases[0] if bases else None
    implements = tuple(bases[1:])
    layer = _classify_layer(class_name, file_path)

    body_node = get_child_by_field(node, "body")
    method_nodes: list[Node] = []
    if body_node is not None:
        for child in body_node.children:
            unwrapped = _unwrap_decorated(child)
            if unwrapped.type == "function_definition":
                method_nodes.append(unwrapped)
    methods = tuple(_method_result_from_node(member, source_bytes) for member in method_nodes)
    fields = (
        _extract_field_definitions(body_node, source_bytes, method_nodes)
        if body_node is not None
        else []
    )

    return PythonClassResult(
        name=class_name,
        kind="class",  # Python엔 별도 interface 문법 없음(ABC는 관례일 뿐)
        layer=layer,
        extends=extends,
        extends_generic_params=(),  # 제네릭 타입 파라미터는 이번 범위에서 추출 안 함
        implements=implements,
        fields=tuple(fields),
        methods=methods,
        qualified_name=class_name,  # 패키지 정보가 파일 하나만 봐선 없어서 이름 그대로
    )


def _extract_field_definitions(
    body_node: Node, source_bytes: bytes, method_nodes: list[Node]
) -> list[FieldResult]:
    """클래스 필드를 두 가지 방식으로 best-effort 추출.

    1. 클래스 바디의 타입 힌트 달린 속성 선언: `x: Type` 또는 `x: Type = value`.
    2. `__init__` 안의 `self.x = SomeClass()` 패턴 — 생성자 호출로 타입을
       추론함. Java/JS와 달리 Python은 필드 타입 선언이 강제가 아니라서,
       1번만으로는 실무 코드에서 필드가 거의 안 잡힘 — 리시버 타입 매칭
       (CALLS 해석에 씀)이 유의미하게 동작하려면 이 패턴 인식이 필요함.
       `ClassName(...)` 형태(대문자 시작 식별자 호출)만 인식해서 팩토리
       함수 호출과의 오탐을 줄임 — 완벽하진 않지만 흔한 관례에 기댄 근사치.
    """
    fields: list[FieldResult] = []
    seen_names: set[str] = set()

    for child in body_node.children:
        if child.type != "expression_statement" or not child.children:
            continue
        inner = child.children[0]
        if inner.type != "assignment":
            continue
        left = get_child_by_field(inner, "left")
        type_node = get_child_by_field(inner, "type")
        if left is None or type_node is None or left.type != "identifier":
            continue
        name = get_node_text(left, source_bytes)
        fields.append(FieldResult(name=name, type=get_node_text(type_node, source_bytes)))
        seen_names.add(name)

    init_node = next(
        (
            node
            for node in method_nodes
            if _function_name(node, source_bytes) == _CONSTRUCTOR_NAME
        ),
        None,
    )
    if init_node is not None:
        init_body = get_child_by_field(init_node, "body")
        if init_body is not None:
            for call_node in find_nodes_by_type(init_body, "call"):
                assignment = call_node.parent
                # tree-sitter Node는 같은 노드를 가리켜도 접근할 때마다 새
                # 래퍼 객체를 만들 수 있어서 `is`가 아니라 `==`로 비교해야 함
                # (id()/== 는 내부적으로 같은 노드인지 정확히 비교해줌).
                if (
                    assignment is None
                    or assignment.type != "assignment"
                    or get_child_by_field(assignment, "right") != call_node
                ):
                    continue
                left = get_child_by_field(assignment, "left")
                if left is None or left.type != "attribute":
                    continue
                receiver_object = get_child_by_field(left, "object")
                attribute_node = get_child_by_field(left, "attribute")
                if (
                    receiver_object is None
                    or receiver_object.type != "identifier"
                    or get_node_text(receiver_object, source_bytes) != "self"
                    or attribute_node is None
                ):
                    continue
                name = get_node_text(attribute_node, source_bytes)
                if name in seen_names:
                    continue
                function_node = get_child_by_field(call_node, "function")
                if function_node is None or function_node.type != "identifier":
                    continue  # 단순 `ClassName()` 형태만 인식, 경로가 붙은 호출은 제외
                type_name = get_node_text(function_node, source_bytes)
                if not type_name[:1].isupper():
                    continue  # 관례상 대문자 시작 = 클래스로 간주(팩토리 함수 오탐 방지)
                fields.append(FieldResult(name=name, type=type_name))
                seen_names.add(name)

    return fields


# ---------- 합성 module 클래스 (최상위 orphan 함수) ----------


def _module_class_name(file_path: str) -> str:
    stem = file_path.rsplit("/", 1)[-1]
    if stem.endswith(".py"):
        stem = stem[: -len(".py")]
    return f"{stem}{_MODULE_CLASS_SUFFIX}"


def _build_module_class_result(
    root_node: Node, source_bytes: bytes, file_path: str
) -> PythonClassResult | None:
    methods: list[PythonMethodResult] = []
    for child in root_node.children:
        unwrapped = _unwrap_decorated(child)
        if unwrapped.type == "function_definition":
            methods.append(_method_result_from_node(unwrapped, source_bytes))

    if not methods:
        return None

    module_name = _module_class_name(file_path)
    return PythonClassResult(
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

    Python도 타입 힌트가 선택적이라 Java처럼 "타입만" 뽑을 수 없음 — 대신
    파라미터 목록 원문(기본값/`*args`/`**kwargs`/타입힌트 포함)을 그대로
    정규화해서 오버로드 유사 상황을 구분하는 용도로 씀.
    normalize_java_parameter_signature는 공백 제거 + 괄호 검증만 하는
    언어 무관 함수라 여기서도 그대로 재사용함.
    """
    params_node = get_child_by_field(node, "parameters")
    if params_node is None:
        return "()"
    return normalize_java_parameter_signature(get_node_text(params_node, source_bytes))


def _extract_receiver(call_node: Node, source_bytes: bytes) -> str | None:
    """call 노드에서 리시버 식별자를 뽑음 (JS의 _extract_receiver와 대응).

    `self.repository.save(...)` -> "repository"
    `self.validate(...)` (한 단계, self 바로 다음이 메서드) -> None
      (같은 클래스/모듈 함수 호출로 취급 — Java/JS의 receiver=None과 동일한 의미)
    `pollRepository.save(...)` (self가 아닌 식별자) -> "pollRepository"
    `foo(...)` (리시버 없음, bare 호출) -> None
    """
    function_node = get_child_by_field(call_node, "function")
    if function_node is None or function_node.type != "attribute":
        return None  # bare identifier(...) 호출 -> 리시버 없음

    object_node = get_child_by_field(function_node, "object")
    if object_node is None:
        return None
    if object_node.type == "identifier":
        text = get_node_text(object_node, source_bytes)
        return None if text == "self" else text
    if object_node.type == "attribute":
        inner_object = get_child_by_field(object_node, "object")
        inner_attribute = get_child_by_field(object_node, "attribute")
        if (
            inner_object is not None
            and inner_object.type == "identifier"
            and get_node_text(inner_object, source_bytes) == "self"
            and inner_attribute is not None
        ):
            return get_node_text(inner_attribute, source_bytes)
    return None


def _extract_invoked_names(body_node: Node, source_bytes: bytes) -> list[MethodCall]:
    calls: list[MethodCall] = []
    for call_node in find_nodes_by_type(body_node, "call"):
        function_node = get_child_by_field(call_node, "function")
        if function_node is None:
            continue
        if function_node.type == "identifier":
            calls.append(MethodCall(receiver=None, name=get_node_text(function_node, source_bytes)))
        elif function_node.type == "attribute":
            attribute_node = get_child_by_field(function_node, "attribute")
            if attribute_node is None:
                continue
            receiver = _extract_receiver(call_node, source_bytes)
            calls.append(
                MethodCall(receiver=receiver, name=get_node_text(attribute_node, source_bytes))
            )
    return calls


def _method_result_from_node(node: Node, source_bytes: bytes) -> PythonMethodResult:
    """function_definition 노드 하나(클래스 메서드든 모듈 최상위 함수든)를
    공용 PythonMethodResult로 변환.
    """
    name = _function_name(node, source_bytes)
    is_constructor = name == _CONSTRUCTOR_NAME
    param_signature = _get_param_signature(node, source_bytes)

    body_node = get_child_by_field(node, "body")
    invoked_calls = _extract_invoked_names(body_node, source_bytes) if body_node is not None else []

    return PythonMethodResult(
        name=name,
        param_signature=param_signature,
        is_constructor=is_constructor,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        text=get_node_text(node, source_bytes),
        api_mapping=None,  # Flask/FastAPI 라우트 데코레이터 매핑은 이번 범위에서 제외
        invoked_calls=tuple(invoked_calls),
    )
