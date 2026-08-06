"""로컬 샘플 저장소를 Java 파서로 돌려보고 결과를 JSON으로 저장하는
수동 검증용 스크립트. 앱 요청 경로의 일부가 아니라 개발 중 눈으로
확인하기 위한 용도.
"""

import dataclasses
import json
from pathlib import Path

from app.parsers.languages.java import parse_java_file

SAMPLE_REPO_PATH = Path(
    r"D:\PJ\repomind-testdata\spring-security-react-ant-design-polls-app\polling-app-server"
)
OUTPUT_PATH = Path(__file__).resolve().parent / "java_parser_output.json"


def main() -> None:
    java_files = sorted(SAMPLE_REPO_PATH.rglob("*.java"))
    if not java_files:
        raise SystemExit(f"No .java files found under {SAMPLE_REPO_PATH}")

    results = []
    for file_path in java_files:
        # CRLF -> LF 통일 (윈도우 체크아웃이면 원본이 CRLF일 수 있음), 경로 구분자도
        # OS 상관없이 "/"로 고정 (id에 그대로 쓰이므로 환경 따라 값이 달라지면 안 됨)
        source_bytes = file_path.read_bytes().replace(b"\r\n", b"\n")
        relative_path = file_path.relative_to(SAMPLE_REPO_PATH).as_posix()
        result = parse_java_file(relative_path, source_bytes)
        results.append(dataclasses.asdict(result))

    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    class_count = sum(len(r["classes"]) for r in results)
    method_count = sum(len(c["methods"]) for r in results for c in r["classes"])
    layer_counts: dict[str, int] = {}
    for r in results:
        for c in r["classes"]:
            layer_counts[c["layer"]] = layer_counts.get(c["layer"], 0) + 1

    print(f"files={len(java_files)}")
    print(f"classes={class_count}")
    print(f"methods={method_count}")
    print(f"layers={layer_counts}")
    print(f"결과 저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
