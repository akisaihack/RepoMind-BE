"""LLM structured-output shape for follow-up question rewriting.

`app/ai/question_rewriter.py`(신규, 2026-08-26)에서 사용 — 세션의 이전 대화를
참고해서 후속 질문을 독립적인 질문으로 재작성하는 LLM 호출의 응답 형태.
`app/dtos/question.py`의 `QuestionClassificationDecision`과 동일한 패턴:
`llm.with_structured_output(QuestionRewriteDecision)`로 씀.
"""

from pydantic import BaseModel, ConfigDict


class QuestionRewriteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rewritten_question: str
    reason: str


__all__ = ["QuestionRewriteDecision"]
