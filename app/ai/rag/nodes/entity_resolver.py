"""② 코드 심볼 매칭 (Entity Resolver) 노드.

역할: 질문 속 도메인 용어(기능명, 클래스명 등)를 실제 코드 심볼 이름과
매칭해서 후보를 찾음. 벡터 검색과 달리 "이름" 자체를 대상으로 하는 가벼운
매칭 (문자열 부분일치 우선, 필요하면 심볼명 임베딩 유사도로 보강).

입력: state["question"]
출력: state["entity_candidates"]

구현 (docs/langgraph_pipeline.md 4.4 / docs/qa_retrieval_part_plan.md Step 4 참고):
- MVP 결정: 우선순위 낮음 — Vector Retriever가 graph_node_id를 통해 더
  안정적으로 시작점을 찾아주기 때문에, 지금은 빈 리스트만 반환하는
  pass-through로 둠. graph_retriever는 entity_candidates가 비어 있어도
  vector_results만으로 정상 동작함(graph_retriever.py 참고).
- 나중에 보강할 때: 심볼 이름 목록을 어디서 가져올지(Neo4j 직접 쿼리 vs
  별도 캐시/인덱스)는 미정 — docs/langgraph_pipeline.md 6번 섹션 참고.
"""

from app.ai.rag.state import QAState


def resolve_entities(state: QAState) -> dict:
    """MVP: 코드 심볼 매칭은 보류하고 빈 리스트만 반환."""
    return {"entity_candidates": []}
