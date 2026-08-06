"""소스 코드 파싱 결과를 그래프(Neo4j) 노드/엣지로 변환하는 로직.

app/graph/mappings.py: 파싱 결과 -> GraphNode/GraphEdge 변환 (순수 함수, DB 접근 없음)
app/graph/repositories/: 실제 Neo4j에 쓰는 쿼리
app/graph/queries/: 실제 Neo4j에서 읽는(검색하는) 쿼리
"""

