"""질문 분류 / 답변 생성 프롬프트 템플릿 모음.

노드 파일(question_analyzer.py, response_composer.py 등)은 프롬프트
문자열을 직접 갖고 있지 않고 여기서 import해서 씀 — 프롬프트를 튜닝할 때
파이프라인 로직 코드를 건드리지 않아도 되게 하기 위함.
"""

from app.dtos.response_generation import QueryIntent

# 질문 유형 분류 프롬프트 (question_analyzer.py에서 사용)
# 4가지 유형: intent | impact | location | flow
QUESTION_CLASSIFICATION_PROMPT = """당신은 코드베이스에 대한 사용자 질문을 아래 4가지 유형 중
정확히 하나로 분류하는 분류기입니다.

- flow: 특정 기능/요청이 처리되는 실행 순서, 호출 흐름을 묻는 질문
  (예: "회원가입 요청이 들어오면 어떤 순서로 처리돼?")
- impact: 특정 코드를 변경했을 때 영향을 받는 범위, 의존 관계를 묻는 질문
  (예: "이 메서드를 고치면 어디에 영향을 줘?")
- intent: 코드가 왜 그렇게 작성됐는지, 변경 이유나 개발 배경(이슈/PR/커밋
  이력)을 묻는 질문 (예: "이 로직은 왜 이렇게 짜여있어?")
- location: 특정 기능/API가 코드 어디에 위치하는지, 어떤 역할을 하는지
  묻는 질문 (예: "로그인 처리하는 코드가 어디에 있어?")

사용자 질문을 읽고 위 4가지 중 가장 적합한 유형 하나를 question_kind로
선택하고, 왜 그렇게 판단했는지 한 문장으로 reason에 적으세요. 애매하면
location을 선택하세요.
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
- 반드시 지정된 JSON 답변 형식만 출력하세요. JSON 문자열 안에서는 Markdown을 사용할 수 있습니다.
- 메서드명, 클래스명, HTTP 경로, 짧은 코드 식별자는 반드시 한 쌍의 백틱으로 감싸세요.
  예: `JwtTokenProvider.validateToken(String)`
- 세 줄 이상의 실제 코드 구문은 언어를 지정한 fenced code block으로 작성하세요. 예: ```java ... ```
- claim의 evidenceIds에는 제공된 사용자용 근거 ID만 사용하세요.
- claim의 citations에는 각 문단 또는 목록 항목의 content와 그 항목에 사용한 evidenceIds만 넣으세요.
- 근거로 확인할 수 없는 내용은 fact로 작성하지 말고 uncertainties에 작성하세요.
- `INTRODUCED_IN`, `HAS_VERSION`, `DELETED_IN`, `DERIVED_FROM`, `CALLS` 같은 내부
  그래프 관계명과 `MethodVersion`, `content_hash`, `source_code`, `node_id`,
  `first_observed` 같은 내부 스키마·필드명을 사용자 답변에 그대로 노출하지 마세요.
- 내부 용어는 사용자가 이해할 수 있는 자연어로 바꾸세요. 예를 들어
  `INTRODUCED_IN`은 "해당 코드 버전이 이 커밋에서 처음 관측됨",
  `DELETED_IN`은 "이 커밋에서 삭제됨", `CALLS`는 "호출함"으로 설명하세요.
- JSON 문자열 안의 사용자 표시 문장은 일반 Unicode와 Markdown으로 작성하고,
  `&#x...;`, `&nbsp;` 같은 HTML entity를 생성하지 마세요.

JSON 답변 형식:
{{
  "summary": "질문에 대한 핵심 답변",
  "claims": [
    {{
      "id": "claim-1",
      "kind": "fact | stated_intent | inference 중 하나",
      "title": "주장 제목",
      "content": "근거를 바탕으로 한 구체적인 설명",
      "evidenceIds": ["제공된 근거 ID"],
      "citations": [
        {{"content": "이 문단 또는 목록 항목", "evidenceIds": ["제공된 근거 ID"]}}
      ]
    }}
  ],
  "uncertainties": ["확인할 수 없거나 추가 검증이 필요한 내용"]
}}
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

사용자에게 표시 가능한 근거:
{evidence_context}
"""

RESPONSE_INTENT_INSTRUCTIONS = {
    QueryIntent.FLOW: "기능이 시작되는 지점부터 종료되는 지점까지 호출 순서 중심으로 설명하세요.",
    QueryIntent.DEPENDENCY: (
        "대상 코드와 이를 호출하거나 의존하는 코드의 관계를 중심으로 설명하세요."
    ),
    QueryIntent.HISTORY: (
        "변경 이력을 커밋 시간순으로 설명하세요. version의 source_code와 diff는 확인된 "
        "변경 사실에만 사용하고, commit.message에 변경 이유가 명시된 경우에만 "
        "stated_intent로 작성하세요. 코드 변화만으로 추정한 이유는 inference로 구분하고, "
        "확인할 수 없는 이유는 uncertainties에 작성하세요. 각 변경 claim에는 해당 "
        "version.evidence_id와 commit.evidence_id 중 제공된 ID만 연결하세요. "
        "first_observed는 현재 분석 데이터에서 처음 관측된 버전일 뿐 실제 Git 최초 "
        "도입을 의미하지 않으므로, 최초 도입 커밋이라고 단정하지 마세요. "
        "INTRODUCED_IN이나 MethodVersion 같은 내부 용어 대신 '현재 분석 데이터에서 "
        "확인되는 코드 버전이 해당 커밋에 연결되어 있다'고 설명하세요."
    ),
    QueryIntent.EXPLANATION: "대상 코드의 역할과 주요 동작을 중심으로 설명하세요.",
}
