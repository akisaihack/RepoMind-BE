"""Parse unified-diff hunk ranges without retaining changed source lines."""

import re
from dataclasses import dataclass

_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


@dataclass(frozen=True, slots=True)
class PatchHunk:
    old_start_line: int
    old_line_count: int
    new_start_line: int
    new_line_count: int


def parse_patch_hunks(patch: str | None) -> tuple[PatchHunk, ...]:
    """Extract every valid unified-diff hunk header from a patch."""
    if not patch:
        return ()

    hunks: list[PatchHunk] = []
    for line in patch.splitlines():
        match = _HUNK_HEADER.match(line)
        if not match:
            continue
        hunks.append(
            PatchHunk(
                old_start_line=int(match.group("old_start")),
                old_line_count=int(match.group("old_count") or 1),
                new_start_line=int(match.group("new_start")),
                new_line_count=int(match.group("new_count") or 1),
            )
        )
    return tuple(hunks)
