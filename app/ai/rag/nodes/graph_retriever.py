"""③ 그래프 탐색 (Graph Retriever) 노드.

역할: Vector Retriever가 찾은 graph_node_id(+ Entity Resolver 후보)를
시작점으로 Neo4j에서 질문 유형에 맞는 관계를 탐색.

입력: state["vector_results"](의 graph_node_id들), state["entity_candidates"],
      state["question_kind"]
출력: state["graph_results"]

구현 계획 (docs/langgraph_pipeline.md 4.6, 2.2, 2.3 / docs/qa_retrieval_part_plan.md
Step 3 참고):
1. state["vector_results"]가 비어 있으면 탐색 시작점이 없으므로
   {"graph_results": {"nodes": [], "edges": []}}을 바로 반환 (방어적 처리).
2. 시작점은 state["vector_results"][0]["graph_node_id"] (유사도 1위 결과).
   entity_candidates는 MVP에서는 참고만(현재 entity_resolver가 빈 리스트를
   반환하므로 사실상 안 씀).
3. state.get("question_kind")에 따라 app.graph.queries.traversal의 함수 중
   하나를 선택:
     flow     -> calls_forward
     impact   -> calls_backward
     intent   -> changed_by_history
     그 외(location 등, question_kind 없음 포함) -> shallow_neighborhood
4. Neo4jClient.from_config(current_app.config)로 클라이언트를 만들어서(스크립트
   들(scripts/import_code_graph.py)과 동일 패턴, with 문으로 자동 close)
   선택한 traversal 함수를 호출.
5. {"graph_results": result} 형태로 반환 (result는 이미 GraphData 호환
   {"nodes": [...], "edges": [...]}).

CHANGED_BY 엣지는 아직 생성 로직이 없음 — PostgreSQL commit_file_change_hunks의
new_start_line/new_line_count와 Method 노드의 start_line/end_line을 겹침
비교해서 만들어야 함(별도 배치 작업, 이 파이프라인 구현 범위 밖이지만
intent 질문에 필요하므로 먼저 해결돼야 함). 그 전까지 changed_by_history는
빈 결과를 반환함 — graph_results가 비어도 evidence_fusion/evidence_validator가
vector_results만으로 자연스럽게 동작하게 둠(정상 동작, 에러 아님).
"""

from flask import current_app

from app.ai.rag.state import QAState
from app.clients.neo4j import Neo4jClient
from app.graph.queries import traversal

_STRATEGY_BY_QUESTION_KIND = {
    "flow": traversal.calls_forward,
    "impact": traversal.calls_backward,
    "intent": traversal.changed_by_history,
}


def search_graph_evidence(state: QAState) -> dict:
    """graph_node_id를 시작점으로 Neo4j를 탐색해서 state["graph_results"]를 채워 반환."""
    vector_results = state.get("vector_results", [])
    if not vector_results:
        return {"graph_results": {"nodes": [], "edges": []}}

    start_node_id = vector_results[0]["graph_node_id"]
    question_kind = state.get("question_kind")
    strategy = _STRATEGY_BY_QUESTION_KIND.get(question_kind, traversal.shallow_neighborhood)

    with Neo4jClient.from_config(current_app.config) as client:
        graph_results = strategy(client, start_node_id)

    return {"graph_results": graph_results}
