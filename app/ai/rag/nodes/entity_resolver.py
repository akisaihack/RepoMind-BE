"""② 코드 심볼 매칭 (Entity Resolver) 노드.

역할: 질문 속 도메인 용어(기능명, 클래스명 등)를 실제 코드 심볼 이름과
매칭해서 후보를 찾음. 벡터 검색과 달리 "이름" 자체를 대상으로 하는 가벼운
매칭 (문자열 부분일치 우선, 필요하면 심볼명 임베딩 유사도로 보강).

입력: state["question"]
출력: state["entity_candidates"]

구현 (docs/langgraph_pipeline.md 4.4 / docs/qa_retrieval_part_plan.md Step 4 참고):
- 질문에서 코드 식별자 후보를 추출하고 repository-scoped code_chunks의
  method/class 이름과 정확히 대조한다.
- 같은 Method의 여러 MethodVersion은 가장 최근 청크 하나만 남긴다.
"""

from app.ai.rag.state import QAState
from app.ai.symbol_extraction import extract_symbol_candidates
from app.extensions import db
from app.repositories.code_chunk import CodeChunkRepository


def resolve_entities(state: QAState) -> dict:
    """질문의 식별자를 실제 코드 청크와 대조해 정확 일치 후보를 반환한다."""
    names = extract_symbol_candidates(state["question"])
    chunks = CodeChunkRepository(db.session).find_by_exact_symbol_names(
        state["github_repository_id"], names
    )

    results = []
    seen_method_ids: set[str] = set()
    for chunk in chunks:
        if chunk.method_node_id in seen_method_ids:
            continue
        seen_method_ids.add(chunk.method_node_id)
        results.append(_to_hit(chunk))

    return {
        "entity_candidates": [
            {
                "name": result.get("method_name") or result.get("class_name") or "",
                "symbol_type": "method" if result.get("method_name") else "class",
                "graph_node_id": result["method_node_id"],
                "confidence": 1.0,
            }
            for result in results
        ],
        "explicit_symbol_names": names,
        "symbol_results": results,
    }


def _to_hit(chunk) -> dict:
    return {
        "graph_node_id": chunk.graph_node_id,
        "method_node_id": chunk.method_node_id,
        "text": chunk.text,
        "similarity": 1.0,
        "path": chunk.path,
        "class_name": chunk.class_name,
        "method_name": chunk.method_name,
        "param_signature": chunk.param_signature,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "api_http_method": chunk.api_http_method,
        "api_path": chunk.api_path,
        "commit_hash": chunk.commit_hash,
    }
