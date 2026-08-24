"""언어별 파서/매퍼 디스패치 레지스트리.

확장자 하나만 보고 "이 파일을 어떤 함수로 파싱하고, 어떤 함수로 그래프에
매핑할지"를 결정함. `app/services/code_graph_import.py`/`chunk_import.py`가
`*.java`를 하드코딩해서 rglob하던 것을, 여기 등록된 확장자 전체를 훑는
방식으로 바꾸기 위한 레이어.

새 언어를 추가할 때 이 파일의 `_SUPPORTED_EXTENSIONS`에 한 줄만 추가하면
됨 — code_graph_import.py/chunk_import.py는 손댈 필요 없음(레지스트리를
통해서만 언어를 알기 때문).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.dtos.graph import GraphDocument
from app.dtos.protocols import FileResultProtocol
from app.graph.mappings import map_java_file, map_javascript_file, map_python_file
from app.parsers.languages.html import parse_html_file
from app.parsers.languages.java import parse_java_file
from app.parsers.languages.javascript import parse_javascript_file
from app.parsers.languages.python import parse_python_file

ParseFn = Callable[[str, bytes], FileResultProtocol]
MapFn = Callable[[int, FileResultProtocol, str], GraphDocument]


@dataclass(frozen=True, slots=True)
class LanguageSupport:
    """확장자 하나에 대응하는 (언어 이름, 파서 함수, 그래프 매퍼 함수) 묶음."""

    language: str
    parse: ParseFn
    map_to_graph: MapFn


# 확장자는 전부 소문자로 등록 — 조회 시에도 소문자로 정규화해서 비교함
# (Windows 체크아웃 등에서 대소문자가 섞여 들어오는 경우 대비).
_SUPPORTED_EXTENSIONS: dict[str, LanguageSupport] = {
    ".java": LanguageSupport(language="java", parse=parse_java_file, map_to_graph=map_java_file),
    ".js": LanguageSupport(
        language="javascript", parse=parse_javascript_file, map_to_graph=map_javascript_file
    ),
    ".jsx": LanguageSupport(
        language="javascript", parse=parse_javascript_file, map_to_graph=map_javascript_file
    ),
    ".py": LanguageSupport(
        language="python", parse=parse_python_file, map_to_graph=map_python_file
    ),
    # HTML 자체는 그래프에 쓸 클래스/함수가 없어서 map_to_graph는 자바스크립트
    # 매퍼를 그대로 재사용함 — parse_html_file()이 인라인 <script>를 뽑아
    # JavaScriptFileResult로 반환하기 때문(app/parsers/languages/html.py 참고).
    ".html": LanguageSupport(
        language="javascript", parse=parse_html_file, map_to_graph=map_javascript_file
    ),
}
# 의도적으로 미지원: .ts/.tsx(타입스크립트 전용 문법 미지원), .jsp(범용
# tree-sitter 문법이 없어서 이번 범위에서 제외 — 실수로 빠뜨린 게 아님).

# node_modules는 JS 지원을 켜는 순간 파일 수가 수만 개로 뛰기 때문에
# discover_source_files가 아예 이 디렉터리들 안으로 들어가지 않게 함.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        "coverage",
        ".next",
        ".pytest_cache",
    }
)


def supported_extensions() -> frozenset[str]:
    return frozenset(_SUPPORTED_EXTENSIONS)


def language_support_for(path: Path) -> LanguageSupport | None:
    """파일 경로의 확장자로 지원 정보를 찾음. 미지원 확장자면 None."""
    return _SUPPORTED_EXTENSIONS.get(path.suffix.lower())


def discover_source_files(repository_path: Path) -> list[Path]:
    """저장소를 한 번 훑어서 지원 확장자 파일만 정렬해서 반환.

    `Path.rglob`이 아니라 `os.walk`를 쓰는 이유: rglob은 먼저 전체를 다 훑은
    다음에 걸러내지만, os.walk는 `dirnames`를 in-place로 잘라내면 그 하위
    디렉터리 안으로 아예 내려가지 않음 — node_modules 하나가 수만 개 파일을
    담고 있어도 그 안을 순회하지 않고 통째로 건너뜀(성능 차이가 실질적임).
    """
    repository_path = repository_path.resolve()
    matched: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repository_path):
        dirnames[:] = [name for name in dirnames if name not in _EXCLUDED_DIR_NAMES]
        for filename in filenames:
            if Path(filename).suffix.lower() in _SUPPORTED_EXTENSIONS:
                matched.append(Path(dirpath) / filename)
    return sorted(matched)


__all__ = [
    "LanguageSupport",
    "discover_source_files",
    "language_support_for",
    "supported_extensions",
]
