"""Method<->Commit 줄 범위 겹침을 비교해서 Neo4j에 CHANGED_BY 관계를 추가하는
1회성 배치 스크립트.

⚠️ 이 스크립트는 어디에서도 자동 호출되지 않음 — 파이프라인
(app/ai/rag/*), qa_service.py, 다른 임포트 스크립트 전부 이 파일을 모름.
독립 실행 전용 도구임. 공유 Neo4j(team2용 인스턴스)에 새로운 관계 타입
(CHANGED_BY)을 실제로 써넣는 작업이므로, **그래프 담당자에게 먼저 알리고
승인받은 뒤에만 --dry-run 없이 실행할 것**
(docs/qa_retrieval_part_plan.md, 2026-08-19 논의 참고).

배경 (docs/langgraph_pipeline.md 2.3절 / Phase 5):
- GitHub 이력 그래프엔 (Commit)-[:CHANGED]->(File)까지만 있고 메서드 단위
  연결이 없음.
- 그런데 코드 그래프의 File 노드와 GitHub 이력 그래프의 File 노드는 같은
  file_key() 공식을 써서 이미 하나로 합쳐져 있음(app/graph/mappings.py,
  app/graph/mappers/github.py) — 그래서 Commit -> File -> Class -> Method
  경로 자체는 이미 존재하지만, 파일 단위라 "이 커밋이 정확히 이 메서드를
  건드렸는지"는 알 수 없음(같은 파일의 관련 없는 다른 메서드까지 다 딸려나옴).
- PostgreSQL commit_file_change_hunks에 커밋별로 정확히 몇 번째 줄을
  바꿨는지(new_start_line/new_line_count) 이미 저장되어 있음 — 이 스크립트는
  그 값을 Method 노드의 start_line/end_line과 겹침 비교해서, 정말로 그
  메서드를 건드린 커밋만 정밀하게 CHANGED_BY로 직접 연결함.

동작:
1. PostgreSQL에서 해당 레포의 CommitFileChange + hunks를 전부 조회.
2. 각 file_path에 대해 file_key()로 Neo4j File 노드를 찾고, 그 아래
   Method 노드들(File -[:DECLARES]-> Class/Interface -[:CONTAINS]-> Method)을
   조회.
3. 각 hunk의 [new_start_line, new_start_line+new_line_count-1]과 Method의
   [start_line, end_line]이 겹치면 (method_key, commit_key) 링크 후보로 수집.
   겹친 구간(overlap_start_line/overlap_end_line)도 같이 기록.
4. --dry-run이 아니면 CodeGraphRepository.link_changed_by()로 일괄 반영.

사용:
  python scripts/link_changed_by.py --github-repository-id 123231656 --dry-run
  python scripts/link_changed_by.py --github-repository-id 123231656
"""

import argparse

from app import create_app
from app.clients.neo4j import Neo4jClient
from app.extensions import db
from app.graph.identifiers import file_key, repository_scoped_key
from app.graph.repositories.code_graph import CodeGraphPersistenceError, CodeGraphRepository
from app.models.commit_file_change import CommitFileChange
from app.repositories.commit_file_change import CommitFileChangeRepository

_METHODS_IN_FILE_QUERY = """
MATCH (:File {key: $file_key})-[:DECLARES]->(:Class|Interface)-[:CONTAINS]->(method:Method)
RETURN method.key AS key, method.start_line AS start_line, method.end_line AS end_line
"""


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> tuple[int, int] | None:
    """두 [start, end] 폐구간(둘 다 포함)이 겹치는 구간을 반환, 안 겹치면 None."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return (start, end) if start <= end else None


def _methods_in_file(client: Neo4jClient, file_key_value: str) -> list[dict]:
    result = client.execute_query(_METHODS_IN_FILE_QUERY, {"file_key": file_key_value})
    return [
        {"key": record["key"], "start_line": record["start_line"], "end_line": record["end_line"]}
        for record in result.records
    ]


def _build_links(
    client: Neo4jClient,
    github_repository_id: int,
    file_changes: list[CommitFileChange],
) -> list[dict]:
    links: list[dict] = []
    methods_cache: dict[str, list[dict]] = {}

    for change in file_changes:
        key = file_key(github_repository_id, change.file_path)
        if key not in methods_cache:
            methods_cache[key] = _methods_in_file(client, key)
        methods = methods_cache[key]
        if not methods:
            continue

        commit_key = repository_scoped_key(github_repository_id, "commit", change.commit_sha)

        for hunk in change.hunks:
            hunk_start = hunk.new_start_line
            hunk_end = hunk.new_start_line + hunk.new_line_count - 1
            for method in methods:
                overlap = _overlap(method["start_line"], method["end_line"], hunk_start, hunk_end)
                if overlap is None:
                    continue
                links.append(
                    {
                        "method_key": method["key"],
                        "commit_key": commit_key,
                        "overlap_start_line": overlap[0],
                        "overlap_end_line": overlap[1],
                    }
                )

    return links


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-repository-id", required=True, type=int)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Neo4j에 실제로 쓰지 않고 몇 개의 CHANGED_BY 링크가 생성될지만 미리 확인.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        file_changes = CommitFileChangeRepository(db.session).list_for_repository(
            args.github_repository_id
        )
        print(f"{len(file_changes)}개의 파일 변경 이력(commit_file_changes) 조회됨.")

        with Neo4jClient.from_config(app.config) as client:
            links = _build_links(client, args.github_repository_id, file_changes)
            print(f"{len(links)}개의 CHANGED_BY 링크 후보 발견.")

            if args.dry_run:
                print("--dry-run 지정됨 — Neo4j에 아무것도 쓰지 않았음.")
                return

            try:
                written = CodeGraphRepository(client).link_changed_by(links)
            except CodeGraphPersistenceError as exc:
                raise SystemExit(f"CHANGED_BY link failed: {exc}") from exc

    print(f"CHANGED_BY link: OK ({written}개 관계 생성/갱신)")


if __name__ == "__main__":
    main()
