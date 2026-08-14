"""Shared graph identifier tests."""

import pytest

from app.graph.identifiers import file_key, normalize_repository_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("./src/App.java", "src/App.java"),
        (r"src\App.java", "src/App.java"),
        ("src//main/./App.java", "src/main/App.java"),
        ("src/generated/../App.java", "src/App.java"),
    ],
)
def test_normalizes_repository_relative_paths(path: str, expected: str) -> None:
    assert normalize_repository_path(path) == expected


@pytest.mark.parametrize("path", ["", "/src/App.java", r"C:\src\App.java", "../App.java"])
def test_rejects_invalid_repository_paths(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_repository_path(path)


def test_file_key_is_repository_scoped() -> None:
    assert file_key(100, "./src/App.java") == "100:file:src/App.java"
    assert file_key(101, r"src\App.java") == "101:file:src/App.java"
