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


def test_ignores_issue_numbers_in_fenced_and_inline_code() -> None:
    body = """See #10 and `example #11`.

```text
Fixes #12
reference #13
```

~~~markdown
#14
~~~
"""

    references = extract_issue_references(None, body)

    assert [(item.issue_number, item.reference_type) for item in references] == [(10, "references")]


def test_keeps_closing_keywords_outside_code() -> None:
    body = """`Fixes #7` is an example.

```text
Closes #8
```

Resolves #9 and see #10.
"""

    references = extract_issue_references(None, body)

    assert [(item.issue_number, item.reference_type) for item in references] == [
        (9, "resolves"),
        (10, "references"),
    ]


def test_supports_multi_backtick_inline_code() -> None:
    references = extract_issue_references(None, "``example `#7` `` and #8")

    assert [(item.issue_number, item.reference_type) for item in references] == [(8, "references")]
