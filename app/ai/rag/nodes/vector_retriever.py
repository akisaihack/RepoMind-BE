"""③ 벡터 검색 (Vector Retriever) 노드.

역할: 질문을 임베딩해서 pgvector(code_chunks 테이블)에서 의미상 유사한
코드 청크를 top-k 검색. 결과의 graph_node_id/method_node_id가 다음 단계
(Graph Retriever)의 시작점이 됨 — Hybrid RAG의 핵심 다리.

입력: state["question"], state["github_repository_id"]
출력: state["vector_results"]

구현 (docs/langgraph_pipeline.md 4.5, 2.1 / docs/qa_retrieval_part_plan.md
Step 2 참고):
1. current_app.config의 AZURE_OPENAI_EMBEDDING_DEPLOYMENT + Azure OpenAI
   클라이언트로 EmbeddingService 생성 (app/api/v1/embeddings.py의
   get_embedding_service()와 동일 패턴).
2. embedding_service.embed(state["question"])로 질문을 벡터로 변환.
3. CodeChunkRepository(db.session).search_similar(query_embedding,
   state["github_repository_id"], top_k=TOP_K) 호출.
4. 반환된 (CodeChunk, distance) 튜플을 state.py의 VectorHit TypedDict
   형태로 변환. similarity = 1 - distance (코사인 거리는 작을수록 유사 ->
   필드명 의미에 맞게 클수록 유사한 값으로 변환).
5. 검색 결과가 없으면 빈 리스트를 그대로 반환 — 방어적 처리, 이후
   evidence_validator가 "근거 부족"으로 자연스럽게 판단하게 둠.
6. state 전체가 아니라 {"vector_results": [...]}만 반환 (LangGraph 노드
   함수 규칙).

에러 처리: 별도로 감싸지 않고 EmbeddingService/SQLAlchemy가 던지는 예외를
그대로 전파 (기존 코드베이스 패턴과 일치, 읽기 전용이라 롤백 로직 불필요).

2026-08-22 업데이트 (MethodVersion 스키마 반영): 팀원이 머지한 버전 관리
스키마 때문에 CodeChunk.graph_node_id는 이제 Method가 아니라 그 시점의
MethodVersion을 가리킴. 대신 CodeChunk에 method_node_id(버전과 무관한
안정적인 Method key)가 새로 생겼음. graph_retriever.py가 질문 유형에 따라
둘 중 하나를 골라 써야 해서, 여기서 둘 다 결과에 담아 넘겨줌. 자세한 배경은
docs/qa_retrieval_part_plan.md "0-2" 섹션 참고.

참고: 2026-08-16 기준 pgvector CREATE EXTENSION이 team2db에서 권한 문제로
막혀 있음(관리자 조치 대기) — 이게 풀려야 실 데이터로 end-to-end 테스트
가능. 그 전까지는 EmbeddingService/CodeChunkRepository를 목(mock)으로
바꿔치기해서 변환 로직(4번)만 단위 테스트로 검증.
"""

from flask import current_app

from app.ai.rag.state import QAState
from app.clients.azure_openai import create_azure_openai_client
from app.extensions import db
from app.repositories.code_chunk import CodeChunkRepository
from app.services.embedding import EmbeddingService

TOP_K = 5


def search_vector_evidence(state: QAState) -> dict:
    """질문을 임베딩해서 pgvector 검색을 수행하고 state["vector_results"]를 채워 반환."""
    deployment = current_app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    client = create_azure_openai_client(current_app.config)
    embedding_service = EmbeddingService(client, deployment)

    query_embedding = embedding_service.embed(state["question"])

    repository = CodeChunkRepository(db.session)
    hits = repository.search_similar(
        query_embedding, state["github_repository_id"], top_k=TOP_K
    )

    return {
        "vector_results": [
            {
                "graph_node_id": chunk.graph_node_id,
                "method_node_id": chunk.method_node_id,
                "text": chunk.text,
                "similarity": 1 - distance,
                "path": chunk.path,
                "class_name": chunk.class_name,
                "method_name": chunk.method_name,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "api_http_method": chunk.api_http_method,
                "api_path": chunk.api_path,
                "commit_hash": chunk.commit_hash,
            }
            for chunk, distance in hits
        ]
    }
