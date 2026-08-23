"""① 질문 유형 분류 노드.

역할: 사용자 질문을 "intent" | "impact" | "location" | "flow" 4가지 중
하나로 분류함 (app/dtos/question.py의 QuestionKind와 동일한 값 집합).

입력: state["question"], (있으면) state["question_kind"]
출력: state["question_kind"]

구현 메모 (2026-08-23, LangChain 패턴으로 확정 — docs/qa_retrieval_part_plan.md
0-5 참고):
- 프론트가 이미 question_kind를 넘겨줬으면 이 노드는 스킵함.
- 없으면 app/ai/question_classifier.py의 QuestionClassifier(LangChain,
  Azure OpenAI nano 배포)로 분류. 실패하면 LOCATION으로 방어적 폴백함
  (question_classifier.py 안에서 처리).
"""

from flask import current_app

from app.ai.question_classifier import create_azure_question_classifier
from app.ai.rag.state import QAState


def classify_question(state: QAState) -> dict:
    """질문 유형을 분류해서 state["question_kind"]를 채워 반환."""
    if state.get("question_kind"):
        return {}  # 프론트가 이미 넘겨줌 — 스킵

    classifier = create_azure_question_classifier(current_app.config)
    question_kind = classifier.classify(state["question"])
    return {"question_kind": question_kind}
