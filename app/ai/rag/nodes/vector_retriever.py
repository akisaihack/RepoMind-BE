"""③ 벡터 검색 (Vector Retriever) 노드.

역할: 질문을 임베딩해서 pgvector(code_chunks 테이블)에서 의미상 유사한
코드 청크를 top-k 검색. 결과의 graph_node_id가 다음 단계(Graph Retriever)의
시작점이 됨 — Hybrid RAG의 핵심 다리.

입력: state["question"], state["github_repository_id"]
출력: state["vector_results"]

구현 메모 (docs/langgraph_pipeline.md 4.5, 2.1 참고):
- app.services.embedding.EmbeddingService.embed(question)으로 질문 임베딩
- app.repositories.code_chunk.CodeChunkRepository에 유사도 검색 메서드가
  아직 없음 — 새로 추가 필요. 예:
    def search_similar(self, query_embedding, github_repository_id, top_k=5)
  pgvector 코사인 거리 연산자 `<=>` 사용, github_repository_id로 필터링.
- 2026-08-16 기준 pgvector CREATE EXTENSION이 team2db에서 권한 문제로
  막혀 있음(관리자 조치 대기) — 이게 풀려야 실 데이터로 테스트 가능.
"""

from app.ai.rag.state import QAState


def search_vector_evidence(state: QAState) -> QAState:
    """질문을 임베딩해서 pgvector 검색을 수행하고 state["vector_results"]를 채워 반환."""
    raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.5 참고")
