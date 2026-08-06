"""그래프(Neo4j) 노드/엣지를 표현하는 범용 DTO.

Neo4j는 스키마리스라서, 타입별로 별도 dataclass(ClassNode, MethodNode, ...)를
만드는 대신 GraphNode(id, type, properties) / GraphEdge(type, source, target,
properties) 형태의 범용 property-bag 구조로 표현함. "Class"인지 "Method"인지,
properties 안에 어떤 키가 들어가는지는 app/graph/mappings.py가 정하는 컨벤션을
따름 (이 파일은 컨테이너 형태만 정의함).

주의: properties가 dict라서 GraphNode/GraphEdge는 hash가 안 됨(set의 원소나
dict의 key로 못 씀). frozen=True는 "필드 재할당 방지" 용도로만 씀.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphNode:
    """그래프의 노드(정점) 하나.

    id는 mappings.py가 부여하는 결정적(deterministic) 문자열 ID임 — DB가
    자동 생성하는 ID가 아니라, 같은 입력이면 항상 같은 id가 나옴. 이래야
    여러 파일을 따로 변환한 뒤 합칠 때 같은 대상(예: 같은 패키지)이 자동으로
    하나로 합쳐짐(Neo4j MERGE 기준 키로 씀).
    """

    id: str
    type: str  # "Package" | "Class" | "Interface" | "Method" | "Endpoint" 등
    properties: dict


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """그래프의 엣지(관계) 하나.

    source/target은 원칙적으로 GraphNode.id를 가리켜야 하지만, mappings.py
    1차 변환 단계에서는 다른 파일에 있는 대상(예: 호출한 메서드, 상속한
    클래스)의 실제 id를 아직 몰라서 이름 문자열을 그대로 넣어두는 경우가
    있음 — 이때는 properties["resolved"] = False로 표시함. 실제 id로
    바꾸는 건 resolve_cross_file_references()의 몫.
    """

    type: str  # "CONTAINS" | "CALLS" | "EXTENDS" | "IMPLEMENTS" | "IMPORTS" | "MANAGES" | "EXPOSES"
    source: str
    target: str
    properties: dict


@dataclass(frozen=True, slots=True)
class GraphDocument:
    """여러 노드/엣지를 하나로 묶은 결과. 보통 파일 하나 또는 프로젝트 전체 단위."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
