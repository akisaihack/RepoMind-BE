"""질문 분류 / 답변 생성 프롬프트 템플릿 모음.

노드 파일(question_analyzer.py, response_composer.py 등)은 프롬프트
문자열을 직접 갖고 있지 않고 여기서 import해서 씀 — 프롬프트를 튜닝할 때
파이프라인 로직 코드를 건드리지 않아도 되게 하기 위함.

아직 구현 전 — docs/langgraph_pipeline.md 4.10 참고.
"""

# 질문 유형 분류 프롬프트 (question_analyzer.py에서 사용 예정)
# 4가지 유형: intent | impact | location | flow
QUESTION_CLASSIFICATION_PROMPT = """아직 작성 전.

app/dtos/chat.py의 ChatRequest.question_kind 값 집합과 반드시 맞출 것:
"intent" | "impact" | "location" | "flow"
"""

# 답변 생성 프롬프트 (response_composer.py에서 사용 예정)
# 핵심 원칙: 근거 없으면 의도를 확정적으로 표현하지 않는다.
# claims[].kind는 "fact" | "stated_intent" | "inference" 중 하나로 강제.
RESPONSE_COMPOSITION_PROMPT = """아직 작성 전.

원칙 (docs/langgraph_pipeline.md, 프로젝트 전체 핵심 원칙):
- 확인된 사실(fact): 코드 또는 변경 이력에서 직접 확인 가능
- 명시된 의도(stated_intent): 커밋/PR/이슈에 이유가 작성되어 있음
- 추론된 의도(inference): 코드 구조를 바탕으로 AI가 추정
근거가 부족하면 의도를 확정적으로 표현하지 말고 uncertainties에 명시할 것.
"""
