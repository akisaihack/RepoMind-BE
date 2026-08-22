"""Run retrieval through real infrastructure and print the generated LLM response.

The question analyzer is intentionally skipped until its LLM classifier is ready.
Pass ``--question-kind`` explicitly to exercise retrieval, answer generation, and
visualization with PostgreSQL, Neo4j, and Azure OpenAI.

Example:
    python scripts/check_qa_response.py \
        --github-repository-id 123231656 \
        --question "로그인 요청이 처리되는 호출 흐름을 설명해줘" \
        --question-kind flow
"""

import argparse
import json
import time
from collections.abc import Callable
from typing import Any

from app import create_app
from app.adapters.response_input_adapter import ResponseInputAdapter
from app.ai.generation.context_builder import LLMContextBuilder
from app.ai.rag.nodes import (
    entity_resolver,
    evidence_fusion,
    evidence_validator,
    graph_retriever,
    response_composer,
    target_selector,
    vector_retriever,
)
from app.dtos.question import QuestionKind


def _run_step(name: str, function: Callable[[dict], dict], state: dict) -> None:
    started = time.perf_counter()
    state.update(function(state))
    elapsed = time.perf_counter() - started
    print(f"- {name}: {elapsed:.2f}초")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="실제 검색 결과로 Azure OpenAI 답변과 시각화를 생성합니다."
    )
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--question-kind",
        required=True,
        choices=[kind.value for kind in QuestionKind],
    )
    parser.add_argument(
        "--show-json",
        action="store_true",
        help="답변 요약 외에 전체 answer/intent/visualization JSON도 출력합니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = create_app()
    state: dict[str, Any] = {
        "question": args.question,
        "github_repository_id": args.github_repository_id,
        "question_kind": QuestionKind(args.question_kind),
        "retry_count": 0,
    }

    with app.app_context():
        print("\n=== 단계별 실행 시간 ===")
        steps = (
            ("코드 심볼 확인", entity_resolver.resolve_entities),
            ("pgvector 검색", vector_retriever.search_vector_evidence),
            ("분석 대상 선택", target_selector.select_target),
            ("Neo4j 검색", graph_retriever.search_graph_evidence),
            ("검색 근거 통합", evidence_fusion.fuse_evidence),
            ("근거 충분성 검증", evidence_validator.validate_evidence_sufficiency),
        )
        for name, function in steps:
            _run_step(name, function, state)

        response_input = ResponseInputAdapter().adapt_qa_state(state)
        llm_context = LLMContextBuilder().build(response_input)
        _run_step("Azure OpenAI 답변 및 시각화 생성", response_composer.compose_answer, state)

    graph_results = state.get("graph_results", {}) or {}
    visualization = state["answer"].get("visualization") or {}

    print("\n=== 검색 결과 ===")
    print(f"- 벡터 검색: {len(state.get('vector_results', []))}건")
    selected = state.get("selected_target") or {}
    print(
        f"- 선택 대상: {selected.get('class_name')}.{selected.get('method_name')} "
        f"({selected.get('selection_source')}, {selected.get('selection_reason')})"
    )
    print(f"- 그래프 노드: {len(graph_results.get('nodes', []))}개")
    print(f"- 그래프 엣지: {len(graph_results.get('edges', []))}개")
    print(f"- 통합 근거: {len(state.get('evidence', []))}건")

    print("\n=== LLM 전용 컨텍스트 ===")
    print(f"- 코드: {len(llm_context.code)}건")
    print(f"- 그래프 관계: {len(llm_context.relations)}건")
    print(f"- 개발 이력: {len(llm_context.history)}건")
    print(f"- 크기: {len(llm_context.model_dump_json(exclude_none=True)):,}자")

    print("\n=== 실제 LLM 답변 ===")
    print(state["answer"]["answer"])

    print("\n=== 시각화 ===")
    print(f"- 유형: {visualization.get('type')}")
    print(f"- 노드: {len(visualization.get('nodes', []))}개")
    print(f"- 엣지: {len(visualization.get('edges', []))}개")

    if args.show_json:
        print("\n=== 전체 응답 JSON ===")
        print(json.dumps(state["answer"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
