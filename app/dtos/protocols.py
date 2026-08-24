"""언어 무관 구조적 계약(Protocol) — 새 언어 DTO가 반드시 만족해야 하는 필드 모양.

app/services/chunking.py의 build_chunks_from_file()과 app/graph/mappings.py의
매퍼 함수들이, 특정 언어(Java)에 묶인 dataclass 대신 "이 모양만 만족하면 어떤
언어든 받아들인다"는 계약을 명시하기 위한 것. 필드 이름이 우연히 일치하는 것에
암묵적으로 의존하지 않고, 여기서 계약을 고정해서 어긋나면 타입 체커가 잡아내게
함. 런타임 동작에는 영향 없음(구조적 타이핑 documentation 목적).

새 언어 파서가 지켜야 할 규칙 (계약):
- ClassResultProtocol.kind는 파서가 이미 "class" | "interface"로 정규화해서
  내보내야 함 (그래프/청크 쪽에서 언어별 분기 없이 그대로 씀).
- 클래스 없이 파일 최상위에 있는 함수(JS/Python의 top-level function)는
  파일당 합성 "module" 클래스 하나에 담아서 이 계약을 그대로 만족시킴
  (app/graph/mappings.py의 language-specific 매퍼가 이 처리를 담당).
"""

from typing import Protocol

from app.dtos.analysis import APIMapping, FieldResult, MethodCall


class MethodResultProtocol(Protocol):
    name: str | None
    param_signature: str
    is_constructor: bool
    start_line: int
    end_line: int
    text: str
    api_mapping: APIMapping | None
    invoked_calls: tuple[MethodCall, ...]


class ClassResultProtocol(Protocol):
    name: str | None
    kind: str  # "class" | "interface" — 파서가 이미 정규화해서 내보내야 함
    layer: str
    extends: str | None
    extends_generic_params: tuple[str, ...]
    implements: tuple[str, ...]
    fields: tuple[FieldResult, ...]
    methods: tuple[MethodResultProtocol, ...]
    qualified_name: str | None


class FileResultProtocol(Protocol):
    path: str
    package: str | None
    imports: tuple[str, ...]
    classes: tuple[ClassResultProtocol, ...]


__all__ = ["ClassResultProtocol", "FileResultProtocol", "MethodResultProtocol"]
