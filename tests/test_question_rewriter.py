"""Question rewriter (follow-up question 재작성) 동작 테스트."""

from unittest.mock import Mock

from app.ai.question_rewriter import QuestionRewriter


def test_rewrite_returns_structured_rewritten_question_when_history_present() -> None:
    rewriter = Mock()
    rewriter.invoke.return_value = {
        "rewritten_question": "CancelController.cancel()을 어떻게 수정해야 해?",
        "reason": "이전 답변에서 언급된 메서드를 명시함",
    }

    result = QuestionRewriter(rewriter).rewrite(
        "그거 어떻게 고쳐?",
        "사용자: 취소 요청은 어디서 처리돼?\n어시스턴트: CancelController.cancel()에서 처리합니다.",
    )

    assert result == "CancelController.cancel()을 어떻게 수정해야 해?"


def test_rewrite_skips_llm_call_when_no_history() -> None:
    rewriter = Mock()

    result = QuestionRewriter(rewriter).rewrite("로그인 흐름을 알려줘", "")

    assert result == "로그인 흐름을 알려줘"
    rewriter.invoke.assert_not_called()


def test_rewrite_falls_back_to_original_question_when_provider_fails() -> None:
    rewriter = Mock()
    rewriter.invoke.side_effect = RuntimeError("provider unavailable")

    result = QuestionRewriter(rewriter).rewrite(
        "그거 어떻게 고쳐?",
        "사용자: 취소 요청은 어디서 처리돼?\n어시스턴트: CancelController.cancel()에서 처리합니다.",
    )

    assert result == "그거 어떻게 고쳐?"


def test_rewrite_falls_back_to_original_when_rewritten_question_is_blank() -> None:
    rewriter = Mock()
    rewriter.invoke.return_value = {"rewritten_question": "   ", "reason": "빈 응답"}

    result = QuestionRewriter(rewriter).rewrite("그거 어떻게 고쳐?", "사용자: ...\n어시스턴트: ...")

    assert result == "그거 어떻게 고쳐?"


def test_rewrite_without_llm_returns_original_question() -> None:
    # LLM 없이 만들어졌을 때(예: 설정 누락 상황을 흉내낸 테스트)의 방어적 폴백.
    result = QuestionRewriter(None).rewrite("그거 어떻게 고쳐?", "사용자: ...\n어시스턴트: ...")

    assert result == "그거 어떻게 고쳐?"
