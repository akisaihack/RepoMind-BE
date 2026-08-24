"""app/parsers/registry.py 테스트 — 확장자 디스패치 + 벤더 디렉터리 제외."""

from pathlib import Path

from app.parsers.registry import discover_source_files, language_support_for, supported_extensions


def test_supported_extensions_include_java_js_python_html_typescript():
    extensions = supported_extensions()
    assert extensions == {".java", ".js", ".jsx", ".py", ".html", ".ts", ".tsx"}


def test_language_support_for_known_and_unknown_extensions():
    assert language_support_for(Path("Foo.java")).language == "java"
    assert language_support_for(Path("Foo.jsx")).language == "javascript"
    assert language_support_for(Path("Foo.js")).language == "javascript"
    assert language_support_for(Path("foo.py")).language == "python"
    # HTML은 인라인 <script>를 JS 파서에 위임하는 구조라 language가 "javascript"
    # (app/parsers/languages/html.py 참고 — HTML 자체는 그래프에 담을 개념이 없음).
    assert language_support_for(Path("index.html")).language == "javascript"
    assert language_support_for(Path("Foo.ts")).language == "typescript"
    assert language_support_for(Path("Foo.tsx")).language == "typescript"
    # 의도적 미지원 — 실수로 빠뜨린 게 아님(JSP는 범용 tree-sitter grammar가
    # 없어서 이번 범위에서 제외).
    assert language_support_for(Path("Foo.jsp")) is None


def test_discover_source_files_excludes_vendor_directories(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.jsx").write_text("// jsx")
    (tmp_path / "src" / "Main.java").write_text("// java")
    (tmp_path / "src" / "notes.ts").write_text("// typescript, now supported")
    (tmp_path / "src" / "widget.tsx").write_text("// tsx, now supported")
    (tmp_path / "src" / "legacy.jsp").write_text("// still unsupported")
    (tmp_path / "scripts" / "cli").mkdir(parents=True)
    (tmp_path / "scripts" / "cli" / "tool.py").write_text("# python")
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "index.html").write_text("<html></html>")

    (tmp_path / "node_modules" / "react").mkdir(parents=True)
    (tmp_path / "node_modules" / "react" / "index.js").write_text("// vendored, must be excluded")

    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "bundle.js").write_text("// build output, must be excluded")

    found = discover_source_files(tmp_path)
    relative = sorted(p.relative_to(tmp_path).as_posix() for p in found)

    assert relative == [
        "public/index.html",
        "scripts/cli/tool.py",
        "src/App.jsx",
        "src/Main.java",
        "src/notes.ts",
        "src/widget.tsx",
    ]


def test_discover_source_files_returns_sorted_list(tmp_path):
    (tmp_path / "b.js").write_text("// b")
    (tmp_path / "a.java").write_text("// a")

    found = discover_source_files(tmp_path)
    assert [p.name for p in found] == ["a.java", "b.js"]
