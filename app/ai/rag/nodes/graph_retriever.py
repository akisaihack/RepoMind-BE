"""③ 그래프 탐색 (Graph Retriever) 노드.

역할: Vector Retriever가 찾은 시작 노드(+ Entity Resolver 후보)를
시작점으로 Neo4j에서 질문 유형에 맞는 관계를 탐색.

입력: state["vector_results"], state["entity_candidates"],
      state["question_kind"]
출력: state["graph_results"]

구현 계획 (docs/langgraph_pipeline.md 4.6, 2.2, 2.3 / docs/qa_retrieval_part_plan.md
Step 3 참고):
1. state["vector_results"]가 비어 있으면 탐색 시작점이 없으므로
   {"graph_results": {"nodes": [], "edges": []}}을 바로 반환 (방어적 처리).
2. 시작점은 Target Selector가 고른 state["selected_target"]에서 뽑음.
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

2026-08-22 업데이트 (MethodVersion 스키마 반영, docs/qa_retrieval_part_plan.md
"0-2" 참고): 팀원이 머지한 버전 관리 스키마 때문에 시작점으로 어떤 id를
쓰느냐가 질문 유형마다 달라짐.
- flow(calls_forward): vector_results[0]["graph_node_id"] 사용 — 벡터로
  실제 매칭된 "그 정확한 버전"에서 호출 관계를 펼치는 게 더 정밀함.
- impact/intent/그 외(location): vector_results[0]["method_node_id"] 사용 —
  CALLS 관계의 도착점, CONTAINS/EXPOSES 등 "메서드 자체"에 걸린 관계들은
  버전이 아니라 Method 노드 기준이라서, 버전 key를 그대로 넘기면 매치되는
  게 없어 항상 빈 결과가 나옴(예전에 있었던 버그 — impact 질문이 항상
  근거 없음으로 나왔던 원인).
"""

from flask import current_app

from app.ai.rag.state import QAState
from app.clients.neo4j import Neo4jClient
from app.dtos.question import QuestionKind
from app.graph.queries import traversal

_STRATEGY_BY_QUESTION_KIND = {
    QuestionKind.FLOW: traversal.calls_forward,
    QuestionKind.IMPACT: traversal.calls_backward,
    QuestionKind.INTENT: traversal.changed_by_history,
}

# flow만 "정확히 매칭된 그 버전"(graph_node_id)에서 출발하고, 나머지는 전부
# 버전과 무관한 "메서드 자체"(method_node_id)에서 출발한다.
_START_ID_FIELD_BY_QUESTION_KIND = {QuestionKind.FLOW: "graph_node_id"}
_DEFAULT_START_ID_FIELD = "method_node_id"


def search_graph_evidence(state: QAState) -> dict:
    """시작 노드를 골라 Neo4j를 탐색해서 state["graph_results"]를 채워 반환."""
    selected_target = state.get("selected_target")
    if selected_target is None:
        vector_results = state.get("vector_results", [])
        selected_target = vector_results[0] if vector_results else None
    if selected_target is None:
        return {"graph_results": {"nodes": [], "edges": []}}

    question_kind = QuestionKind(state.get("question_kind", QuestionKind.LOCATION))
    strategy = _STRATEGY_BY_QUESTION_KIND.get(question_kind, traversal.shallow_neighborhood)
    start_id_field = _START_ID_FIELD_BY_QUESTION_KIND.get(
        question_kind, _DEFAULT_START_ID_FIELD
    )
    start_node_id = selected_target[start_id_field]

    with Neo4jClient.from_config(current_app.config) as client:
        graph_results = strategy(client, start_node_id)

    return {"graph_results": graph_results}
