"""내 파트(질문 분류~근거 통합)를 실제 인프라(pgvector/Neo4j)에 붙여서
손으로 확인하는 개발용 스크립트. mock이 아니라 진짜 결과/소요 시간을 봄.

scripts/check_pipeline_skeleton.py와의 차이: 그건 7개 노드를 전부 더미로
바꿔치기해서 "그래프 배관"만 확인함. 이건 반대로 내가 실제로 구현한 5개
노드(entity_resolver/vector_retriever/graph_retriever/evidence_fusion/
evidence_validator)를 진짜 함수 그대로, 손으로 순서대로 이어서 실행함.

run_qa_pipeline()을 안 쓰는 이유: 그건 컴파일된 그래프로 7개 노드(question_analyzer,
response_composer 포함)를 전부 실행하는데, 이 두 노드는 아직
NotImplementedError라서 끝까지 못 감(각각 Step 7, 그리고 팀원 파트).
question_kind는 --question-kind로 직접 넘겨서 question_analyzer를 스킵하는
경로를 씀 — 이건 프론트가 이미 question_kind를 넘겨주는 정상 케이스와
동일한 경로임(app/dtos/chat.py의 ChatRequest.question_kind 참고).

사전 준비 (이 스크립트를 실행하는 쪽 — 로컬 환경에서):
1. pgvector `CREATE EXTENSION` 권한이 풀려 있어야 함
   (docs/langgraph_pipeline_checklist.md Phase 0)
2. .env에 AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY /
   AZURE_OPENAI_EMBEDDING_DEPLOYMENT / NEO4J_URI / NEO4J_USERNAME /
   NEO4J_PASSWORD 실제 값이 설정돼 있어야 함
3. `python scripts/import_chunks.py --github-repository-id ... --repository-path ... --commit-hash ...`
   로 코드 청크(pgvector) 적재
4. `python scripts/import_code_graph.py --github-repository-id ... --repository-path ...`
   로 코드 그래프(Neo4j) 적재
5. (intent 질문까지 보고 싶으면) scripts/link_changed_by.py까지 실행
   — 단, 그래프 담당자 승인 먼저 받을 것(docs/qa_retrieval_part_plan.md 7번 참고)

사용 예:
  python scripts/check_my_part.py \\
      --github-repository-id 123231656 \\
      --question "로그인 프로세스 흐름을 알려줘" \\
      --question-kind flow
"""

import argparse
import time

from app import create_app
from app.ai.rag.nodes import (
    entity_resolver,
    evidence_fusion,
    evidence_validator,
    graph_retriever,
    vector_retriever,
)


def _run_timed(label: str, fn, state: dict) -> dict:
    start = time.perf_counter()
    result = fn(state)
    elapsed = time.perf_counter() - start
    print(f"\n=== {label} ({elapsed:.2f}초) ===")
    print(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--question-kind",
        choices=["intent", "impact", "location", "flow"],
        default=None,
        help="Step 7(question_analyzer)이 아직 없어서 직접 지정 — 프론트가 넘겨주는 경우와 동일 경로.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        state: dict = {
            "question": args.question,
            "github_repository_id": args.github_repository_id,
            "question_kind": args.question_kind,
            "retry_count": 0,
        }

        state.update(_run_timed("① entity_resolver", entity_resolver.resolve_entities, state))
        state.update(_run_timed("② vector_retriever", vector_retriever.search_vector_evidence, state))
        state.update(_run_timed("③ graph_retriever", graph_retriever.search_graph_evidence, state))
        state.update(_run_timed("④ evidence_fusion", evidence_fusion.fuse_evidence, state))
        state.update(
            _run_timed(
                "⑤ evidence_validator", evidence_validator.validate_evidence_sufficiency, state
            )
        )

    print("\n=== 최종 요약 ===")
    evidence = state.get("evidence", [])
    print(f"근거 {len(evidence)}건, is_sufficient={state.get('is_sufficient')}")
    for item in evidence:
        print(f"  - [{item['type']}] {item['title']} ({item['location']})")


if __name__ == "__main__":
    main()
