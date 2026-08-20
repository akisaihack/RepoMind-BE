"""Shared graph identifier tests."""

import pytest

from app.graph.identifiers import (
    class_key,
    constructor_key,
    file_key,
    java_qualified_name,
    method_content_hash,
    method_key,
    method_version_key,
    normalize_java_parameter_signature,
    normalize_repository_path,
)


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


def test_builds_nested_java_qualified_name() -> None:
    assert java_qualified_name("com.example", ("Outer",), "Inner") == (
        "com.example.Outer.Inner"
    )


def test_stable_code_keys_distinguish_overloads_and_constructors() -> None:
    class_id = class_key(100, "./src/App.java", "Class", "com.example.App")

    assert class_id == "100:class:src/App.java:com.example.App"
    assert method_key(class_id, "save", "( List < String > )") == (
        f"{class_id}:method:save:(List<String>)"
    )
    assert method_key(class_id, "save", "(Order)") != method_key(
        class_id, "save", "(Order,boolean)"
    )
    assert constructor_key(class_id, "App", "()") != method_key(class_id, "App", "()")


def test_normalizes_parameter_signature_formatting() -> None:
    assert normalize_java_parameter_signature("(Map < String, List < Long > >, int [])") == (
        "(Map<String,List<Long>>,int[])"
    )


def test_method_version_key_changes_only_with_normalized_source() -> None:
    method_id = "100:class:src/App.java:com.example.App:method:save:()"
    first_hash = method_content_hash("void save() {\r\n  run();   \r\n}")
    same_hash = method_content_hash("void save() {\n  run();\n}")
    changed_hash = method_content_hash("void save() {\n  stop();\n}")

    assert first_hash == same_hash
    assert first_hash != changed_hash
    assert method_version_key(method_id, first_hash) == (
        f"{method_id}:version:{first_hash}"
    )
