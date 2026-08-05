"""Unified-diff hunk parser tests."""

from app.parsers.patch import PatchHunk, parse_patch_hunks


def test_parses_multiple_hunk_variants() -> None:
    patch = """@@ -72,5 +72,10 @@ method
@@ -10 +10,3 @@ another
@@ -0,0 +1,20 @@ new file
@@ -15,8 +0,0 @@ removed
"""

    assert parse_patch_hunks(patch) == (
        PatchHunk(72, 5, 72, 10),
        PatchHunk(10, 1, 10, 3),
        PatchHunk(0, 0, 1, 20),
        PatchHunk(15, 8, 0, 0),
    )


def test_missing_or_invalid_patch_returns_no_hunks() -> None:
    assert parse_patch_hunks(None) == ()
    assert parse_patch_hunks("not a unified diff") == ()
