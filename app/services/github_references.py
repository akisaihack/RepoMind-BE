"""Extract same-repository Issue references from GitHub text."""

import re

from app.dtos.github import IssueReferenceDTO

_ISSUE_PATTERN = re.compile(r"(?<![\w/])#(?P<number>\d+)\b")
_FENCE_OPEN_PATTERN = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})")
_INLINE_CODE_PATTERN = re.compile(r"(?P<fence>`+).*?(?P=fence)", re.DOTALL)


def extract_issue_references(
    title: str | None,
    body: str | None,
) -> tuple[IssueReferenceDTO, ...]:
    """Return unique resolve/reference links, preferring resolve semantics."""
    text = "\n".join(_remove_markdown_code(part) for part in (title, body) if part)
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


def _remove_markdown_code(text: str) -> str:
    """Replace fenced and inline code with whitespace before parsing references."""
    visible_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    for line in text.splitlines(keepends=True):
        stripped = line.lstrip(" \t")
        if fence_character is not None:
            closing_pattern = rf"{re.escape(fence_character)}{{{fence_length},}}[ \t]*(?:\n)?$"
            closing = re.match(closing_pattern, stripped)
            if closing:
                fence_character = None
                fence_length = 0
            visible_lines.append("\n" if line.endswith("\n") else " ")
            continue

        opening = _FENCE_OPEN_PATTERN.match(line)
        if opening:
            fence = opening.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            visible_lines.append("\n" if line.endswith("\n") else " ")
            continue

        visible_lines.append(line)

    visible_text = "".join(visible_lines)
    return _INLINE_CODE_PATTERN.sub(" ", visible_text)
