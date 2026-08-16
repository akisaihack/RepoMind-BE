"""② 코드 심볼 매칭 (Entity Resolver) 노드.

역할: 질문 속 도메인 용어(기능명, 클래스명 등)를 실제 코드 심볼 이름과
매칭해서 후보를 찾음. 벡터 검색과 달리 "이름" 자체를 대상으로 하는 가벼운
매칭 (문자열 부분일치 우선, 필요하면 심볼명 임베딩 유사도로 보강).

입력: state["question"]
출력: state["entity_candidates"]

구현 메모 (docs/langgraph_pipeline.md 4.4 참고):
- 우선순위 낮음 — Vector Retriever가 graph_node_id를 통해 더 안정적으로
  시작점을 찾아주기 때문에, MVP에서는 이 노드를 건너뛰고 vector_retriever
  결과만으로 graph_retriever를 태워도 됨. 시간 없으면 가장 먼저 뺄 후보.
- 심볼 이름 목록을 어디서 가져올지(Neo4j 직접 쿼리 vs 별도 캐시/인덱스)는
  미정 — docs/langgraph_pipeline.md 6번 섹션 미해결 이슈 참고.
"""

from app.ai.rag.state import QAState


def resolve_entities(state: QAState) -> QAState:
    """질문 속 용어를 코드 심볼 후보와 매칭해서 state["entity_candidates"]를 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.4 참고")
