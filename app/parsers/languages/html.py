"""HTML 전용 Tree-sitter 추출 로직.

HTML 자체는 클래스/함수 개념이 없어서 별도 DTO나 그래프 매퍼를 만들지
않음 — 대신 `<script>` 태그 안의 인라인 JS만 뽑아서
app.parsers.languages.javascript.parse_javascript_file()에 그대로 위임함.
즉 HTML 파일 하나의 파싱 결과는 JavaScriptFileResult로 나오고,
app/graph/mappings.py의 map_javascript_file()을 그대로 재사용함(레지스트리
등록도 동일 — app/parsers/registry.py 참고). `<script src="...">`처럼 외부
파일을 가리키기만 하고 본문이 없는 태그는 (raw_text가 비어있어서) 자동으로
건너뛰어짐 — 외부 스크립트 자체는 그 파일 확장자(.js)로 별도 파싱됨.

여러 <script> 블록이 한 파일에 있으면, 블록마다 합성 경로
("index.html#script0", "index.html#script1", ...)를 파서 내부적으로만
붙여서 각 블록의 orphan 함수가 서로 다른 module 클래스로 분리되게 하고,
최종적으로는 전부 원래 HTML 파일 경로 하나의 결과로 합침(File 노드가
스크립트 개수만큼 중복 생기지 않도록).
"""

import tree_sitter_html as tshtml
from tree_sitter import Language, Node

from app.dtos.analysis import JavaScriptFileResult
from app.parsers.languages.javascript import parse_javascript_file
from app.parsers.tree_sitter import build_parser, find_nodes_by_type, parse_source

HTML_LANGUAGE = Language(tshtml.language())


def parse_html_file(path: str, source_bytes: bytes) -> JavaScriptFileResult:
    """HTML 소스 파일 하나를 파싱해서, 안에 있는 모든 인라인 `<script>` 블록의
    JS 파싱 결과를 하나로 합쳐 반환함. 인라인 스크립트가 하나도 없으면
    (또는 전부 `src="..."` 외부 참조/빈 태그면) classes/imports가 빈 결과를
    반환함 — 에러가 아님, HTML만 있고 로직 없는 파일은 흔함.
    """
    parser = build_parser(HTML_LANGUAGE)
    tree = parse_source(parser, source_bytes)
    root_node = tree.root_node

    all_classes = []
    all_imports: list[str] = []
    for index, script_node in enumerate(find_nodes_by_type(root_node, "script_element")):
        raw_text_node = _find_raw_text_child(script_node)
        if raw_text_node is None:
            continue
        script_bytes = source_bytes[raw_text_node.start_byte : raw_text_node.end_byte]
        if not script_bytes.strip():
            continue  # src="..."로만 된 외부 스크립트 태그(본문 없음) — 건너뜀

        # 합성 경로는 module 클래스 이름(app.parsers.languages.javascript의
        # _module_class_name)이 스크립트 블록마다 겹치지 않게 하려는 용도로만
        # 씀 — 최종 반환 결과의 path는 아래에서 원래 HTML 경로로 되돌림.
        synthetic_path = f"{path}#script{index}"
        script_result = parse_javascript_file(synthetic_path, script_bytes)
        all_classes.extend(script_result.classes)
        all_imports.extend(script_result.imports)

    return JavaScriptFileResult(
        path=path,
        package=None,
        imports=tuple(all_imports),
        classes=tuple(all_classes),
    )


def _find_raw_text_child(script_node: Node) -> Node | None:
    """script_element의 본문(raw_text) 자식을 찾음. tree-sitter-html
    문법이 raw_text에 필드 이름을 안 붙여줘서 타입으로 직접 찾음.
    본문이 아예 없는 형태(자기 닫힘 태그 등)면 None.
    """
    return next((child for child in script_node.children if child.type == "raw_text"), None)
