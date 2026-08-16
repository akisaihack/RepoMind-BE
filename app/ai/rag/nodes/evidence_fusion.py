"""④ 근거 통합 (Evidence Fusion) 노드.

역할: Vector Retriever + Graph Retriever 결과를 하나로 합침 — 중복 제거,
관련도 순 재정렬, app.dtos.chat.Evidence 호환 형태로 정리.

입력: state["vector_results"], state["graph_results"]
출력: state["evidence"]

구현 메모 (docs/langgraph_pipeline.md 4.7 참고):
- LLM 호출 없이 순수 로직으로 가능(정렬/중복제거 규칙 기반).
- 각 근거 항목은 최종적으로 app.dtos.chat.Evidence(type, title, location,
  description, excerpt)와 호환되는 형태를 목표로 함.
"""

from app.ai.rag.state import QAState


def fuse_evidence(state: QAState) -> QAState:
    """벡터+그래프 결과를 통합해서 state["evidence"]를 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.7 참고")
