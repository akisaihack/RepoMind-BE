"""Data Transfer Objects for Chat Query API."""

from dataclasses import dataclass, field
from typing import Literal

from app.dtos.question import QuestionKind


@dataclass
class ChatRequest:
    """
    질의응답(Chat) API 요청 데이터 규격.

    <pre>
        사용자가 입력한 질문과 선택적인 질문 유형(kind)을 포함.
    </pre>

    @param question 사용자가 입력한 실제 질문 텍스트
    @param question_kind 프론트엔드 또는 질문 분석기가 결정한 질문 유형
    """

    question: str
    question_kind: QuestionKind | None = None


@dataclass
class GraphNode:
    id: str
    type: Literal["api", "symbol", "commit"]
    label: str
    detail: str | None = None


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    type: str
    label: str | None = None


@dataclass
class GraphData:
    """Public graph contract.

    ``kind == 'flow'`` exposes only ``calls``, ``http_calls``, and ``handled_by``
    edges. Every node must be an endpoint or a method connected to one of them.
    """

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    kind: Literal["flow", "impact", "history", "relationship"] | None = None


@dataclass
class Evidence:
    id: str
    type: Literal["code", "itsm", "commit"]
    title: str
    location: str
    description: str
    excerpt: str | None = None
    fullExcerpt: str | None = None
    startLine: int | None = None
    endLine: int | None = None
    excerptStartLine: int | None = None
    excerptEndLine: int | None = None
    hasMoreBefore: bool = False
    hasMoreAfter: bool = False


@dataclass
class Claim:
    id: str
    kind: Literal["fact", "stated_intent", "inference"]
    title: str
    content: str
    evidenceIds: list[str]
    citations: list["ClaimCitation"] = field(default_factory=list)


@dataclass
class ClaimCitation:
    """근거 배지를 붙일 하나의 답변 문단 또는 목록 항목."""

    content: str
    evidenceIds: list[str]


@dataclass
class Confidence:
    level: Literal["high", "medium", "low"]
    reason: str


@dataclass
class ChatResponseData:
    """
    프론트엔드의 StructuredAnswer 스펙에 대응하는 최종 질의응답 응답 데이터.

    <pre>
        답변 요약, 상세 주장(claims), 출처 근거(evidence), 코드 관계 그래프(graph) 등
        프론트엔드 렌더링에 필요한 모든 AI 분석 결과를 한 객체에 담아 반환함.
    </pre>

    @param summary 전체 답변 요약
    @param claims 상세 주장 및 분석 내용 배열
    @param evidence 주장의 근거가 된 출처(코드, 이슈 등) 배열
    @param confidence AI의 답변 신뢰도 및 판단 이유
    @param graph 코드/메서드 간 호출 관계 그래프 데이터 (노드 및 엣지)
    @param uncertainties AI가 판단하기 불확실했던 부분 (선택 사항)
    @param suggestedQuestions 후속 질문 추천 목록 (선택 사항)
    """

    summary: str
    claims: list[Claim]
    evidence: list[Evidence]
    confidence: Confidence
    graph: GraphData
    uncertainties: list[str] = field(default_factory=list)
    suggestedQuestions: list[str] = field(default_factory=list)
