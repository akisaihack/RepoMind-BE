"""로컬 샘플 저장소를 Java 파서 -> 청킹까지 돌려보고 결과를 JSON으로 저장하는
수동 검증용 스크립트. 앱 요청 경로의 일부가 아니라 개발 중 눈으로 확인하기
위한 용도.
"""

import dataclasses
import json
from pathlib import Path

from app.parsers.languages.java import parse_java_file
from app.services.chunking import build_chunks_from_file

SAMPLE_REPO_PATH = Path(
    r"D:\PJ\repomind-testdata\spring-security-react-ant-design-polls-app\polling-app-server"
)
OUTPUT_PATH = Path(__file__).resolve().parent / "chunking_output.json"

# 더미값이 아니라 실제 GitHub 저장소(callicoder/spring-security-react-ant-design
# -polls-app)의 실제 값. graph_node_id/File 노드 key가 이 repository id를
# 그대로 쓰기 때문에, 나중에 이 샘플 저장소의 GitHub 이력을 실제로 수집하면
# Repository/Commit 노드와 곧바로 연결됨.
SAMPLE_GITHUB_REPOSITORY_ID = 123231656  # github.com/callicoder/spring-security-react-ant-design-polls-app
SAMPLE_COMMIT_HASH = "362fad90cab17e76453b3b9e273c594de6ee3d7f"  # 로컬 체크아웃된 master HEAD


def main() -> None:
    java_files = sorted(SAMPLE_REPO_PATH.rglob("*.java"))
    if not java_files:
        raise SystemExit(f"No .java files found under {SAMPLE_REPO_PATH}")

    chunks = []
    for file_path in java_files:
        # CRLF -> LF 통일, 경로 구분자도 OS 상관없이 "/"로 고정
        # (자세한 이유는 scripts/check_java_parser.py 참고)
        source_bytes = file_path.read_bytes().replace(b"\r\n", b"\n")
        relative_path = file_path.relative_to(SAMPLE_REPO_PATH).as_posix()
        file_result = parse_java_file(relative_path, source_bytes)
        chunks.extend(
            build_chunks_from_file(SAMPLE_GITHUB_REPOSITORY_ID, file_result, SAMPLE_COMMIT_HASH)
        )

    output = [dataclasses.asdict(chunk) for chunk in chunks]
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    layer_counts: dict[str, int] = {}
    for chunk in chunks:
        layer_counts[chunk.layer] = layer_counts.get(chunk.layer, 0) + 1

    text_lengths = [len(chunk.text) for chunk in chunks]

    print(f"files={len(java_files)}")
    print(f"chunks={len(chunks)}")
    print(f"layers={layer_counts}")
    print(f"text length min/avg/max={min(text_lengths)}/{sum(text_lengths) // len(text_lengths)}/{max(text_lengths)}")
    print(f"결과 저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
