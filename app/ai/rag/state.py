"""LangGraph 파이프라인의 공유 State 스키마.

각 노드는 이 State를 입력받아 자기 책임인 필드만 채워서 반환한다. 필드
목록/설명은 docs/langgraph_pipeline.md의 4.1 섹션과 항상 동기화할 것.

설계 원칙: graph_results/evidence/answer는 app/dtos/chat.py의
GraphData/Evidence/ChatResponseData와 필드가 호환되도록 맞춘다 — 파이프라인
결과를 API 응답으로 바꿀 때 변환 로직을 최소화하기 위함.
"""

from typing import NotRequired, TypedDict

# Evidence Validator가 재검색으로 돌아갈 수 있는 최대 횟수. 이 값을 넘기면
# 근거가 부족해도 강제로 Response Composer로 넘어가서 "확정 어려움"을
# 포함한 답변을 만든다 (무한 루프 방지).
MAX_RETRIES = 2


class EntityCandidate(TypedDict):
    """Entity Resolver가 찾은 코드 심볼 후보 하나."""

    name: str
    symbol_type: str  # "class" | "method" 등
    graph_node_id: str
    confidence: float


class VectorHit(TypedDict):
    """Vector Retriever가 pgvector에서 찾은 청크 검색 결과 하나.

    graph_node_id / method_node_id 구분 (2026-08-22, MethodVersion 스키마
    반영): graph_node_id는 벡터로 매칭된 "그 시점의 정확한 코드 버전"
    (Neo4j MethodVersion 노드) key, method_node_id는 버전과 무관한
    "메서드 자체"(Neo4j Method 노드) key. graph_retriever.py가 질문
    유형에 따라 둘 중 하나를 골라 그래프 탐색 시작점으로 씀 — 자세한 이유는
    docs/qa_retrieval_part_plan.md의 "0-2" 섹션 참고.
    """

    graph_node_id: str
    method_node_id: str
    text: str
    similarity: float
    path: str
    class_name: str | None
    method_name: str | None
    commit_hash: str


class QAState(TypedDict):
    """파이프라인 전체에서 공유되는 상태.

    입력 단계(question, github_repository_id 등)를 제외한 나머지 필드는
    NotRequired로 표시함 — 파이프라인이 진행되면서 순차적으로 채워지기
    때문에 시작 시점엔 없어도 되는 필드들.
    """

    # --- 입력 (파이프라인 시작 시 이미 채워져 있어야 함) ---
    question: str
    github_repository_id: int
    conversation_id: NotRequired[str | None]

    # --- ① Question Analyzer가 채움 ---
    # 프론트가 ChatRequest.question_kind로 이미 넘겨줄 수도 있음 — 그 경우
    # 이 노드는 검증만 하거나 스킵.
    question_kind: NotRequired[str]  # "intent" | "impact" | "location" | "flow"

    # --- ② Entity Resolver가 채움 ---
    entity_candidates: NotRequired[list[EntityCandidate]]

    # --- ③ Vector Retriever가 채움 ---
    vector_results: NotRequired[list[VectorHit]]

    # --- ③ Graph Retriever가 채움 ---
    graph_results: NotRequired[dict]  # app.dtos.chat.GraphData 호환 형태 목표

    # --- ④ Evidence Fusion이 채움 ---
    evidence: NotRequired[list[dict]]  # app.dtos.chat.Evidence 호환 형태 목표

    # --- ⑤ Evidence Validator가 채움 (조건부 엣지 분기 기준) ---
    is_sufficient: NotRequired[bool]
    retry_count: NotRequired[int]

    # --- ⑥ Response Composer가 채움 (최종 출력) ---
    answer: NotRequired[dict]  # app.dtos.chat.ChatResponseData 호환 형태 목표
