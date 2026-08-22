"""질문 분류 / 답변 생성 프롬프트 템플릿 모음.

노드 파일(question_analyzer.py, response_composer.py 등)은 프롬프트
문자열을 직접 갖고 있지 않고 여기서 import해서 씀 — 프롬프트를 튜닝할 때
파이프라인 로직 코드를 건드리지 않아도 되게 하기 위함.
"""

from app.dtos.question import QuestionKind
from app.dtos.response_generation import QueryIntent

# 질문 유형 분류 프롬프트 (question_analyzer.py에서 사용 예정)
# 4가지 유형: intent | impact | location | flow
QUESTION_CLASSIFICATION_PROMPT = f"""아직 작성 전.

app.dtos.question.QuestionKind 값 중 하나를 반환할 것:
{", ".join(kind.value for kind in QuestionKind)}
"""

TARGET_SELECTION_SYSTEM_PROMPT = """당신은 코드 검색 결과의 분석 대상 선택기입니다.
사용자 질문을 실제로 처리하는 코드 후보 하나를 반드시 선택하세요.
메서드명뿐 아니라 HTTP 경로, 코드 내용, 파일 위치를 함께 판단하세요.
제공된 후보 밖의 대상을 만들지 말고 후보의 0부터 시작하는 인덱스만 선택하세요.
"""

TARGET_SELECTION_USER_PROMPT = """사용자 질문: {question}

분석 대상 후보:
{candidates}
"""

# 답변 생성 공통 프롬프트. LLM은 조회 근거를 설명하는 역할만 맡고,
# React Flow 데이터는 VisualizationBuilder가 실제 DB 결과로 생성한다.
RESPONSE_SYSTEM_PROMPT = """당신은 코드베이스 분석 도우미입니다.

제공된 검색 결과만 근거로 사용자의 질문에 답변하세요.

규칙:
- 제공되지 않은 코드나 관계를 임의로 생성하지 마세요.
- 코드 구조, 호출 관계, 개발 이력은 제공된 정보만 사용하세요.
- 사용자가 이해하기 쉽게 핵심 내용을 설명하세요.
- 조회 결과가 부족한 경우 추측하지 말고 정보가 부족함을 명확히 설명하세요.
- React Flow 노드나 엣지, JSON 시각화 데이터는 생성하지 마세요.
"""

RESPONSE_USER_PROMPT = """사용자 질문: {question}
질문 유형: {intent}
분석 대상: {target}
유형별 지침: {intent_instruction}

관련 코드 조회 결과:
{code_context}

코드 그래프 조회 결과:
{graph_context}

개발 이력 조회 결과:
{history_context}
"""

RESPONSE_INTENT_INSTRUCTIONS = {
    QueryIntent.FLOW: "기능이 시작되는 지점부터 종료되는 지점까지 호출 순서 중심으로 설명하세요.",
    QueryIntent.DEPENDENCY: (
        "대상 코드와 이를 호출하거나 의존하는 코드의 관계를 중심으로 설명하세요."
    ),
    QueryIntent.HISTORY: (
        "Issue, PR, Commit과 코드 변경의 관계를 중심으로 변경 이유를 설명하세요."
    ),
    QueryIntent.EXPLANATION: "대상 코드의 역할과 주요 동작을 중심으로 설명하세요.",
}
