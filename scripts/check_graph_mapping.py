"""로컬 샘플 저장소를 Java 파서 -> 그래프 매핑까지 돌려보고 결과를 JSON으로
저장하는 수동 검증용 스크립트. 앱 요청 경로의 일부가 아니라 개발 중 눈으로
확인하기 위한 용도.

scripts/check_java_parser.py가 "파싱이 잘 되는지"를 봤다면, 이 스크립트는
"파싱 결과가 노드/엣지로 잘 변환되고, 파일 간 CALLS/EXTENDS 등이 잘
해석(resolve)되는지"를 봄.
"""

import dataclasses
import json
from pathlib import Path

from app.graph.mappings import map_java_file, resolve_cross_file_references
from app.parsers.languages.java import parse_java_file

SAMPLE_REPO_PATH = Path(
    r"D:\PJ\repomind-testdata\spring-security-react-ant-design-polls-app\polling-app-server"
)
OUTPUT_PATH = Path(__file__).resolve().parent / "graph_mapping_output.json"


def main() -> None:
    java_files = sorted(SAMPLE_REPO_PATH.rglob("*.java"))
    if not java_files:
        raise SystemExit(f"No .java files found under {SAMPLE_REPO_PATH}")

    documents = []
    for file_path in java_files:
        # CRLF -> LF 통일, 경로 구분자도 OS 상관없이 "/"로 고정
        # (자세한 이유는 scripts/check_java_parser.py 참고)
        source_bytes = file_path.read_bytes().replace(b"\r\n", b"\n")
        relative_path = file_path.relative_to(SAMPLE_REPO_PATH).as_posix()
        file_result = parse_java_file(relative_path, source_bytes)
        documents.append(map_java_file(file_result))

    final_document = resolve_cross_file_references(documents)

    output = {
        "nodes": [dataclasses.asdict(node) for node in final_document.nodes],
        "edges": [dataclasses.asdict(edge) for edge in final_document.edges],
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    node_type_counts: dict[str, int] = {}
    for node in final_document.nodes:
        node_type_counts[node.type] = node_type_counts.get(node.type, 0) + 1

    edge_type_counts: dict[str, int] = {}
    resolved_counts: dict[str, int] = {"resolved": 0, "ambiguous": 0, "external": 0, "n/a": 0}
    for edge in final_document.edges:
        edge_type_counts[edge.type] = edge_type_counts.get(edge.type, 0) + 1
        if edge.properties.get("ambiguous"):
            resolved_counts["ambiguous"] += 1
        elif edge.properties.get("external"):
            resolved_counts["external"] += 1
        elif edge.properties.get("resolved") is True:
            resolved_counts["resolved"] += 1
        else:
            resolved_counts["n/a"] += 1

    print(f"files={len(java_files)}")
    print(f"nodes={len(final_document.nodes)} {node_type_counts}")
    print(f"edges={len(final_document.edges)} {edge_type_counts}")
    print(f"edge resolution={resolved_counts}")
    print(f"결과 저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
