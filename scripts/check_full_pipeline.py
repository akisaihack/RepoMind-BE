"""전체 파이프라인(8개 노드)을 run_qa_pipeline()으로 실제 실행해서
결과를 파일로 남기는 점검 스크립트.

scripts/check_my_part.py와의 차이: 그건 question_analyzer/response_composer를
빼고 5개 노드만 손으로 이어붙인 스크립트임(그 두 노드가 구현되기 전에 쓰던 것).
이제 8개 노드가 다 구현됐으니, 이 스크립트는 run_qa_pipeline()을 그대로 호출해서
검색·분류·답변 생성 경로를 점검함. 세션 조회·메시지 영속화까지 포함한 API E2E는
README의 "실제 RAG Chat E2E 검증" 절차를 사용함.

중요: run_qa_pipeline()의 반환값은 QueryResponseState 호환 dict
{"answer": str, "intent": str, "visualization": dict | None} 뿐임.
Neo4j 그래프 탐색 결과(graph_results — nodes/edges dump)는 파이프라인 중간
상태라서 반환값에 안 들어있음. 콘솔에서 CALLS/HAS_VERSION 관계로 가득한
긴 dict가 보였다면 그건 최종 answer가 아니라 그래프 검색 노드 내부 결과를
직접 print한 것 — 최종 채점 기준은 항상 answer_dict["answer"] 텍스트임.

사용법:
  python scripts/check_full_pipeline.py --github-repository-id 123231656

출력: scripts/pipeline_test_results.json
  (질문별 question_kind, 소요 시간, answer, intent, visualization을 정리해서 저장)
"""

import argparse
import json
import time

from app import create_app
from app.ai.rag.pipeline import run_qa_pipeline

TEST_QUESTIONS = [
    {
        "label": "flow-1 (투표)",
        "kind": "flow",
        "question": "사용자가 투표를 하면 요청이 어떤 순서로 처리돼?",
    },
    {
        "label": "flow-2 (로그인)",
        "kind": "flow",
        "question": "로그인 요청이 들어오면 인증은 어떤 순서로 처리돼?",
    },
    {
        "label": "impact (PollRepository)",
        "kind": "impact",
        "question": "PollRepository.findById 메서드를 변경하면 어떤 코드들이 영향을 받아?",
    },
    {
        "label": "location (투표 결과 계산)",
        "kind": "location",
        "question": "투표 결과(득표 수)를 계산하는 코드는 어디에 있어?",
    },
    {
        "label": "intent (JwtAuthenticationFilter)",
        "kind": "intent",
        "question": "JwtAuthenticationFilter는 왜 이렇게 작성됐어?",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument(
        "--skip-classifier",
        action="store_true",
        help=(
            "question_kind를 TEST_QUESTIONS의 값으로 직접 넘겨서 Step 7(LLM 분류)을 "
            "스킵함. 기본은 넘기지 않음 — question_analyzer가 실제로 분류하게 해서 "
            "Step 7 정확도까지 같이 검증함."
        ),
    )
    parser.add_argument("--output", default="scripts/pipeline_test_results.json")
    args = parser.parse_args()

    app = create_app()
    results = []

    with app.app_context():
        for item in TEST_QUESTIONS:
            print(f"\n=== {item['label']} ===")
            start = time.perf_counter()
            try:
                answer_dict = run_qa_pipeline(
                    question=item["question"],
                    github_repository_id=args.github_repository_id,
                    question_kind=item["kind"] if args.skip_classifier else None,
                )
                elapsed = time.perf_counter() - start
                answer_text = answer_dict.get("answer") or ""
                print(f"  ({elapsed:.2f}초) intent={answer_dict.get('intent')}")
                print(f"  answer: {answer_text[:200]}{'...' if len(answer_text) > 200 else ''}")
                results.append(
                    {
                        "label": item["label"],
                        "expected_kind": item["kind"],
                        "question": item["question"],
                        "elapsed_sec": round(elapsed, 2),
                        "result": answer_dict,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - 테스트 스크립트: 실패해도 다음 질문 계속 진행
                elapsed = time.perf_counter() - start
                print(f"  실패 ({elapsed:.2f}초): {exc!r}")
                results.append(
                    {
                        "label": item["label"],
                        "expected_kind": item["kind"],
                        "question": item["question"],
                        "elapsed_sec": round(elapsed, 2),
                        "error": repr(exc),
                    }
                )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n결과 {len(results)}건을 {args.output}에 저장함.")


if __name__ == "__main__":
    main()
