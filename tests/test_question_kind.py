"""Shared question kind tests."""

import pytest

from app.dtos.question import QuestionKind


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("flow", QuestionKind.FLOW),
        ("impact", QuestionKind.IMPACT),
        ("intent", QuestionKind.INTENT),
        ("location", QuestionKind.LOCATION),
    ],
)
def test_question_kind_parses_supported_api_values(
    raw_value: str, expected: QuestionKind
) -> None:
    assert QuestionKind(raw_value) is expected


def test_question_kind_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        QuestionKind("unknown")
