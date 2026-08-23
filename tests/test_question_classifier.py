"""Question classifier behavior tests."""

from unittest.mock import Mock

from app.ai.question_classifier import QuestionClassifier
from app.dtos.question import QuestionKind


def test_classifier_returns_structured_question_kind() -> None:
    classifier = Mock()
    classifier.invoke.return_value = {"question_kind": "impact", "reason": "수정 영향 질문"}

    result = QuestionClassifier(classifier).classify("이 메서드를 수정하면 어디가 영향받아?")

    assert result is QuestionKind.IMPACT


def test_classifier_falls_back_to_location_when_provider_fails() -> None:
    classifier = Mock()
    classifier.invoke.side_effect = RuntimeError("provider unavailable")

    result = QuestionClassifier(classifier).classify("왜 이렇게 구현했어?")

    assert result is QuestionKind.LOCATION
