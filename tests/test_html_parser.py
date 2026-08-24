"""app/parsers/languages/html.py 단위 테스트.

HTML 자체는 별도 DTO가 없고 인라인 <script> 내용을 JS 파서에 위임한 결과
(JavaScriptFileResult)를 그대로 반환하므로, 여기서는 "위임이 제대로 되는지 +
여러 <script> 블록/외부 스크립트가 올바르게 처리되는지"만 검증함.
"""

from app.parsers.languages.html import parse_html_file

MULTI_SCRIPT_SRC = b"""<!DOCTYPE html>
<html>
<head>
<script>
  function greet(name) { return "hi " + name; }
</script>
</head>
<body>
  <div id="root"></div>
  <script src="bundle.js"></script>
  <script type="text/javascript">
    class Widget {
      render() { return greet("hi"); }
    }
  </script>
</body>
</html>
"""


def test_extracts_classes_from_multiple_script_blocks():
    result = parse_html_file("public/index.html", MULTI_SCRIPT_SRC)
    assert result.path == "public/index.html"
    assert result.package is None
    assert len(result.classes) == 2

    names = {c.name for c in result.classes}
    assert "Widget" in names
    assert any(name.endswith("$module") for name in names)


def test_external_script_with_no_inline_body_is_skipped():
    src = b'<script src="bundle.js"></script>\n<script src="vendor.js"></script>\n'
    result = parse_html_file("index.html", src)
    assert result.classes == ()


def test_file_with_no_script_tags_returns_empty_result():
    result = parse_html_file("index.html", b"<html><body><div>hello</div></body></html>")
    assert result.classes == ()
    assert result.imports == ()


def test_orphan_functions_in_different_script_blocks_do_not_collide():
    src = b"""
    <script>function helper() { return 1; }</script>
    <script>function helper() { return 2; }</script>
    """
    result = parse_html_file("dup.html", src)
    module_class_names = [c.name for c in result.classes]
    # 서로 다른 <script> 블록의 합성 module 클래스는 이름이 겹치면 안 됨
    # (합성 경로에 스크립트 인덱스를 붙여서 구분함).
    assert len(module_class_names) == len(set(module_class_names))
    assert len(module_class_names) == 2
