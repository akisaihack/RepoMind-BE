"""④ 근거 통합 (Evidence Fusion) 노드.

역할: Vector Retriever + Graph Retriever 결과를 하나로 합침 — 중복 제거,
관련도 순 재정렬, app.dtos.chat.Evidence 호환 형태로 정리.

입력: state["vector_results"], state["graph_results"]
출력: state["evidence"]

구현 (docs/langgraph_pipeline.md 4.7 / docs/qa_retrieval_part_plan.md Step 5 참고):
- LLM 호출 없이 순수 로직 — vector_results(pgvector 청크)와
  graph_results["nodes"](Neo4j 탐색 노드)를 각각 app.dtos.chat.Evidence
  호환 dict(id, type, title, location, description, excerpt)로 변환해서
  합침.
- type은 지금은 전부 "code"로 고정 — vector/graph 둘 다 코드 근거만
  다루기 때문(CHANGED_BY 배치가 아직 실행 전이라 "commit"/"itsm" 타입
  근거는 아직 안 나옴. 나중에 graph_results에 Commit/Issue 노드가 섞여
  들어오면 여기서 타입 분기 추가 필요).
- id(=graph_node_id) 기준으로 중복 제거 — 같은 메서드가 vector 검색과
  graph 탐색 양쪽에서 다 나올 수 있음(예: 시작점 노드 자신).
"""

from app.ai.rag.state import QAState


def fuse_evidence(state: QAState) -> dict:
    """벡터+그래프 결과를 통합해서 state["evidence"]를 채워 반환."""
    vector_results = state.get("vector_results", [])
    graph_results = state.get("graph_results", {}) or {}

    evidence: list[dict] = []
    for hit in vector_results:
        evidence.append(
            {
                "id": hit["graph_node_id"],
                "type": "code",
                "title": hit.get("method_name") or hit.get("class_name") or hit.get("path", ""),
                "location": hit.get("path", ""),
                "description": _truncate(hit.get("text", ""), 200),
                "excerpt": hit.get("text"),
            }
        )

    for node in graph_results.get("nodes", []):
        node_id = node.get("id")
        if node_id is None:
            continue
        evidence.append(
            {
                "id": node_id,
                "type": "code",
                "title": node.get("label", node_id),
                "location": node.get("detail") or "",
                "description": node.get("label", ""),
                "excerpt": None,
            }
        )

    seen: set[str] = set()
    deduped: list[dict] = []
    for item in evidence:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)

    return {"evidence": deduped}


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
