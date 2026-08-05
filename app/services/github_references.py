"""Extract same-repository Issue references from GitHub text."""

import re

from app.dtos.github import IssueReferenceDTO

_ISSUE_PATTERN = re.compile(r"(?<![\w/])#(?P<number>\d+)\b")


def extract_issue_references(
    title: str | None,
    body: str | None,
) -> tuple[IssueReferenceDTO, ...]:
    """Return unique resolve/reference links, preferring resolve semantics."""
    text = "\n".join(part for part in (title, body) if part)
    resolved: set[int] = set()

    # GitHub closing keywords may be followed by multiple issue numbers.
    closing_pattern = re.compile(
        r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
        r"(?P<issues>#\d+(?:\s*(?:,|and)\s*#\d+)*)",
        re.IGNORECASE,
    )
    for match in closing_pattern.finditer(text):
        resolved.update(int(value) for value in re.findall(r"#(\d+)", match.group("issues")))

    referenced = {int(match.group("number")) for match in _ISSUE_PATTERN.finditer(text)}
    referenced -= resolved

    return tuple(
        [
            *(IssueReferenceDTO(number, "resolves") for number in sorted(resolved)),
            *(IssueReferenceDTO(number, "references") for number in sorted(referenced)),
        ]
    )
