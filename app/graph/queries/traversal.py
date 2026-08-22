"""Neo4j 코드 그래프 탐색(traversal) Cypher 쿼리 함수 모음.

app/ai/rag/nodes/graph_retriever.py가 question_kind별로 이 중 하나를 골라
호출함. app/graph/repositories/code_graph.py는 "저장"만 담당하고 "조회"
로직은 여기 없었음 — 이 파일이 그 빈틈을 채움.

노드/엣지 저장 컨벤션 재확인 (app/graph/mappings.py, app/graph/repositories/
code_graph.py 참고):
- 모든 노드는 MERGE (node:Label {key: ...})로 저장됨. key 속성이 곧
  graph_node_id(pgvector 청크의 graph_node_id와 동일한 값) — 탐색 시작점은
  항상 이 key로 찾는다: MATCH (start {key: $start_node_id})
- Method 노드 속성: name, signature, class_name, start_line, end_line
  (+API 매핑 메서드면 http_method, path)
- Class/Interface 노드 속성: name, layer, path
- Endpoint 노드 속성: http_method, path
- 관계 타입: CONTAINS, CALLS, EXTENDS, IMPLEMENTS, IMPORTS, MANAGES, EXPOSES
  (app/graph/repositories/code_graph.py의 ALLOWED_RELATIONSHIP_TYPES)

구현 (docs/langgraph_pipeline.md 4.6, 2.2 / docs/qa_retrieval_part_plan.md
Step 3 참고):

- depth는 f-string으로 쿼리에 직접 넣음(가변 길이 경로는 파라미터 바인딩이
  안 되는 Cypher 자체 제약). depth는 사용자 입력이 아니라 코드 상수라
  인젝션 위험 없음.
- changed_by_history: CHANGED_BY 관계는 아직 그래프에 없음(별도 배치 작업
  대기, docs/langgraph_pipeline_checklist.md Phase 5). 지금 짜놔도 매치되는
  게 없어서 자연스럽게 빈 결과 반환(Cypher는 매치 실패해도 에러 없이 빈
  result) — Phase 5 완료되면 코드 수정 없이 그대로 동작함.
- _path_to_graph_dict(records): 공통 변환 헬퍼. 각 레코드의 모든 값 중
  "path처럼 생긴" 값(.nodes/.relationships 속성을 가진 값 — 실제
  neo4j.graph.Path와 duck-typing으로 호환, 테스트에서 가짜 객체로 대체하기
  쉽게 isinstance 대신 hasattr로 판별)을 찾아서 그 안의 노드/관계를
  app.dtos.chat.GraphData 호환 {"nodes": [...], "edges": [...]}로 합침.
  - node.type: Neo4j 라벨이 "Endpoint"면 "api", 그 외(Method/Class/
    Interface)는 "symbol" (mock_chat.py 예시와 동일 규칙)
  - node.label: Method는 f"{class_name}.{name}", Class/Interface는 name,
    Endpoint는 f"{http_method} {path}"
  - node.id: Neo4j의 key 속성 그대로 사용
  - key(node)/(source,type,target) 기준으로 중복 노드·엣지 제거
"""

from app.clients.neo4j import Neo4jClient

DEFAULT_CALLS_DEPTH = 3
DEFAULT_NEIGHBORHOOD_DEPTH = 2


def calls_forward(client: Neo4jClient, start_node_id: str, depth: int = DEFAULT_CALLS_DEPTH) -> dict:
    """flow: CALLS 관계를 depth까지 순방향 탐색."""
    query = f"""
    MATCH path = (start {{key: $start_node_id}})-[:CALLS*1..{depth}]->(end)
    RETURN path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records)


def calls_backward(client: Neo4jClient, start_node_id: str, depth: int = DEFAULT_CALLS_DEPTH) -> dict:
    """impact: CALLS 역방향 — 누가 이 메서드를 호출하는지."""
    query = f"""
    MATCH path = (caller)-[:CALLS*1..{depth}]->(start {{key: $start_node_id}})
    RETURN path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records)


def shallow_neighborhood(
    client: Neo4jClient, start_node_id: str, depth: int = DEFAULT_NEIGHBORHOOD_DEPTH
) -> dict:
    """location: 관계 타입 제한 없이 depth까지만 얕게 탐색."""
    query = f"""
    MATCH path = (start {{key: $start_node_id}})-[*1..{depth}]-(neighbor)
    RETURN path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records)


def changed_by_history(client: Neo4jClient, start_node_id: str) -> dict:
    """intent: CHANGED_BY -> REFERENCES/RESOLVES -> Issue.

    ⚠️ CHANGED_BY 엣지가 아직 그래프에 없음 — Phase 5(별도 배치 작업) 완료
    전까지는 빈 결과만 반환됨(정상 동작, 에러 아님).
    """
    query = """
    MATCH path = (start {key: $start_node_id})-[:CHANGED_BY]->(commit)
    OPTIONAL MATCH extended = (commit)-[:REFERENCES|RESOLVES]->(issue)
    RETURN path, extended
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _path_to_graph_dict(result.records)


def _looks_like_path(value) -> bool:
    """neo4j.graph.Path와 duck-typing으로 호환되는 값인지 판별.

    isinstance(value, neo4j.graph.Path) 대신 hasattr로 판별하는 이유: 실제
    Path/Node/Relationship은 드라이버 내부에서만 생성 가능해서, 단위
    테스트에서 이 판별 로직을 그대로 검증하려면 같은 인터페이스(.nodes/
    .relationships)를 가진 가짜 객체로 대체할 수 있어야 함.
    """
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def _node_type(node) -> str:
    return "api" if "Endpoint" in node.labels else "symbol"


def _node_label(node) -> str:
    labels = node.labels
    if "Endpoint" in labels:
        return f"{node.get('http_method', '')} {node.get('path', '')}".strip()
    if "Method" in labels:
        class_name = node.get("class_name")
        name = node.get("name", "")
        return f"{class_name}.{name}" if class_name else name
    return node.get("name") or node.get("key", "")


def _node_detail(node) -> str | None:
    labels = node.labels
    if "Method" in labels:
        return node.get("signature")
    if "Class" in labels or "Interface" in labels:
        return node.get("path")
    return None


def _to_graph_node(node) -> dict:
    return {
        "id": node.get("key"),
        "type": _node_type(node),
        "label": _node_label(node),
        "detail": _node_detail(node),
    }


def _to_graph_edge(relationship) -> dict:
    source_key = relationship.start_node.get("key")
    target_key = relationship.end_node.get("key")
    return {
        "id": f"{source_key}-{relationship.type}-{target_key}",
        "source": source_key,
        "target": target_key,
        "type": relationship.type,
        "label": relationship.type,
    }


def _path_to_graph_dict(records: list) -> dict:
    """Neo4j 쿼리 결과 레코드 리스트를 GraphData 호환 {"nodes", "edges"} dict로 변환."""
    nodes_by_id: dict[str, dict] = {}
    edges_by_key: dict[tuple, dict] = {}

    for record in records:
        for value in record.values():
            if value is None or not _looks_like_path(value):
                continue
            for node in value.nodes:
                key = node.get("key")
                if key and key not in nodes_by_id:
                    nodes_by_id[key] = _to_graph_node(node)
            for relationship in value.relationships:
                edge_key = (
                    relationship.start_node.get("key"),
                    relationship.type,
                    relationship.end_node.get("key"),
                )
                if edge_key not in edges_by_key:
                    edges_by_key[edge_key] = _to_graph_edge(relationship)

    return {"nodes": list(nodes_by_id.values()), "edges": list(edges_by_key.values())}
