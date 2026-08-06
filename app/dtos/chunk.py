"""pgvector에 저장할 코드 청크(chunk) DTO.

app/services/chunking.py가 이 형태로 결과를 반환함. 청크 하나는 보통 메서드
또는 생성자 하나에 대응함(메서드 단위 청킹). text 필드가 실제로 임베딩할
문자열이고, 나머지는 검색 결과를 보여줄 때/필터링할 때 쓰는 메타데이터.
"""

from dataclasses import dataclass

from app.dtos.analysis import APIMapping


@dataclass(frozen=True, slots=True)
class CodeChunk:
    """메서드/생성자 하나에 대응하는 코드 청크."""

    id: str
    text: str  # 임베딩 대상 텍스트 (문맥 헤더 + 실제 소스코드)
    path: str
    package: str | None
    class_name: str | None
    class_kind: str  # "class" 또는 "interface"
    layer: str
    method_name: str | None
    param_signature: str
    is_constructor: bool
    start_line: int
    end_line: int
    api_mapping: APIMapping | None
