"""③ 그래프 탐색 (Graph Retriever) 노드.

역할: Vector Retriever가 찾은 graph_node_id(+ Entity Resolver 후보)를
시작점으로 Neo4j에서 질문 유형에 맞는 관계를 탐색.

입력: state["vector_results"](의 graph_node_id들), state["entity_candidates"],
      state["question_kind"]
출력: state["graph_results"]

구현 메모 (docs/langgraph_pipeline.md 4.6, 2.2, 2.3 참고):
- question_kind별 탐색 전략:
    flow     -> CALLS 관계를 depth N까지
    intent   -> CHANGED_BY(Symbol->Commit, 아직 그래프에 없음!) ->
                REFERENCES/RESOLVES -> Issue
    impact   -> CALLS의 역방향(누가 이 메서드를 호출하는지)
    location -> depth 1~2 정도만 얕게
- CHANGED_BY 엣지는 아직 생성 로직이 없음 — PostgreSQL
  commit_file_change_hunks의 new_start_line/new_line_count와 Method 노드의
  start_line/end_line을 겹침 비교해서 만들어야 함(별도 배치 작업, 이
  파이프라인 구현 범위 밖이지만 intent/impact 질문에 필요하므로 먼저
  해결돼야 함).
- Cypher 쿼리 함수들 아직 하나도 작성 안 됨 — app.clients.neo4j.Neo4jClient
  사용.
"""

from app.ai.rag.state import QAState


def search_graph_evidence(state: QAState) -> QAState:
    """graph_node_id를 시작점으로 Neo4j를 탐색해서 state["graph_results"]를 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.6 참고")
