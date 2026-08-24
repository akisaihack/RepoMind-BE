"""HTML 파서(app/parsers/languages/html.py)가 잘 동작하는지 눈으로 확인하는
수동 검증용 스크립트. Flask/DB/Neo4j 전혀 필요 없음 — 순수 파싱 로직만 테스트함.

두 가지를 확인함:
1. 대상 리포(폴링앱)의 실제 public/index.html — CRA 기본 템플릿이라 인라인
   <script> 코드가 없는 게 정상이라, 여기서는 "에러 없이 도는지 + 0개 나오는
   게 맞는지"만 확인함 (0개가 나온다고 파서가 고장난 게 아님, 원본에 애초에
   추출할 JS 코드가 없는 것뿐).
2. 스크립트에 내장된 합성(가짜) HTML 샘플 — 실제로 <script> 안에 클래스/함수가
   있을 때 제대로 뽑히는지를 눈으로 확인하기 위한 용도.
"""

import dataclasses
import json
from pathlib import Path

from app.parsers.languages.html import parse_html_file

REAL_HTML_PATH = Path(
    r"D:\PJ\repomind-testdata\spring-security-react-ant-design-polls-app"
    r"\polling-app-client\public\index.html"
)
OUTPUT_PATH = Path(__file__).resolve().parent / "html_parser_output.json"

# 실제 대상 리포엔 인라인 <script>가 없어서, 파서가 제대로 뽑아내는지 눈으로
# 보려면 이렇게 직접 만든 샘플이 필요함.
SYNTHETIC_SAMPLE_HTML = b"""<!DOCTYPE html>
<html>
<head>
<script>
  function greet(name) {
    return "hi " + name;
  }
  function shout(name) {
    return greet(name).toUpperCase();
  }
</script>
</head>
<body>
  <div id="root"></div>
  <script src="bundle.js"></script>
  <script type="text/javascript">
    class VoteWidget {
      render() {
        return shout("world");
      }
    }
  </script>
</body>
</html>
"""


def _summarize(label: str, path: str, source_bytes: bytes) -> dict:
    result = parse_html_file(path, source_bytes)
    class_summaries = [
        {"name": c.name, "methods": [m.name for m in c.methods]} for c in result.classes
    ]
    print(f"\n[{label}] path={path}")
    print(f"  classes found: {len(result.classes)}")
    for summary in class_summaries:
        print(f"    - {summary['name']}: methods={summary['methods']}")
    return {
        "label": label,
        "path": path,
        "classes": class_summaries,
        "result": dataclasses.asdict(result),
    }


def main() -> None:
    outputs = []

    if REAL_HTML_PATH.is_file():
        source_bytes = REAL_HTML_PATH.read_bytes()
        outputs.append(_summarize("실제 대상 리포 (index.html)", "public/index.html", source_bytes))
    else:
        print(f"(참고) 실제 파일을 못 찾음 — 건너뜀: {REAL_HTML_PATH}")

    outputs.append(_summarize("합성 샘플 (스크립트 내장)", "sample.html", SYNTHETIC_SAMPLE_HTML))

    OUTPUT_PATH.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {OUTPUT_PATH}")

    synthetic = next(o for o in outputs if o["label"].startswith("합성"))
    names = {c["name"] for c in synthetic["classes"]}
    expected = {"sample.html#script0$module", "VoteWidget"}
    if names == expected:
        print("\n✅ 합성 샘플 검증 통과 — 두 <script> 블록 모두 정상 추출됨.")
    else:
        print(f"\n❌ 예상과 다름: expected={expected} actual={names}")


if __name__ == "__main__":
    main()
