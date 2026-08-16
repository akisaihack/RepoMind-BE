"""pgvector에 저장할 코드 청크(chunk) DTO.

app/services/chunking.py가 이 형태로 결과를 반환함. 청크 하나는 보통 메서드
또는 생성자 하나에 대응함(메서드 단위 청킹). text 필드가 실제로 임베딩할
문자열이고, 나머지는 검색 결과를 보여줄 때/필터링할 때 쓰는 메타데이터.

graph_node_id는 app/graph/mappings.py가 만드는 Method 노드 id와 항상
동일한 값(같은 class_index/method_index, 같은 id 공식을 재사용해서 계산함).
이 값으로 pgvector 검색 결과를 Neo4j의 Method 노드로 바로 연결할 수 있음
(Hybrid RAG의 "벡터로 시작점 찾고 그래프로 깊이 탐색" 구조의 핵심 다리).

github_repository_id/commit_hash는 이 청크가 어느 저장소, 어느 커밋 시점의
코드 스냅샷인지 나타냄 — 둘 다 더미값이 아니라 실제 GitHub 저장소 id와
실제 커밋 SHA가 들어가야 함. GitHub 커밋 이력 그래프(Commit/Issue/
PullRequest 노드)와 연결하거나, 인덱스 증분 갱신 시 최신 여부를 판단할 때 씀.
"""

from dataclasses import dataclass

from app.dtos.analysis import APIMapping


@dataclass(frozen=True, slots=True)
class CodeChunk:
    """메서드/생성자 하나에 대응하는 코드 청크."""

    id: str
    graph_node_id: str  # Neo4j Method 노드 id와 동일 (app/graph/mappings.py 공식 재사용)
    text: str  # 임베딩 대상 텍스트 (문맥 헤더 + 실제 소스코드)
    path: str
    github_repository_id: int  # 실제 GitHub 저장소 id (더미값 금지)
    commit_hash: str  # 이 코드 스냅샷의 실제 커밋 SHA (더미값 금지)
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
