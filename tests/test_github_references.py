"""Issue-reference extraction tests."""

from app.services.github_references import extract_issue_references


def test_extracts_resolved_and_referenced_issues() -> None:
    references = extract_issue_references("Implement feature #9", "Closes #7, #8 and mentions #10")

    assert [(item.issue_number, item.reference_type) for item in references] == [
        (7, "resolves"),
        (8, "resolves"),
        (9, "references"),
        (10, "references"),
    ]


def test_resolution_takes_precedence_and_cross_repository_reference_is_ignored() -> None:
    references = extract_issue_references(None, "Fixes #7 and see #7 or owner/repo#11")

    assert [(item.issue_number, item.reference_type) for item in references] == [(7, "resolves")]


def test_empty_text_has_no_references() -> None:
    assert extract_issue_references(None, None) == ()
