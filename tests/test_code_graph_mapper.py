"""Repository-scoped Java code graph mapping tests."""

from app.dtos.analysis import FieldResult, JavaClassResult, JavaFileResult, JavaMethodResult
from app.graph.mappings import map_java_file, resolve_cross_file_references
from app.parsers.languages.java import parse_java_file


def _map(repository_id: int, path: str = "src/App.java"):
    method = JavaMethodResult("name", "()", False, 1, 1, "", None, ())
    classes = (
        JavaClassResult("Named", "interface", "Other", None, (), (), (), (method,)),
        JavaClassResult("App", "class", "Other", None, (), ("Named",), (), (method,)),
    )
    result = JavaFileResult(path, "com.example", (), classes)
    return map_java_file(repository_id, result, "abc123")


def test_creates_shared_file_and_declares_relationships() -> None:
    document = _map(100, r".\src\App.java")
    file_node = next(node for node in document.nodes if node.type == "File")
    declarations = [edge for edge in document.edges if edge.type == "DECLARES"]

    assert file_node.id == "100:file:src/App.java"
    assert file_node.properties["path"] == "src/App.java"
    assert {edge.source for edge in declarations} == {file_node.id}
    assert len(declarations) == 2
    assert {node.type for node in document.nodes} >= {"Class", "Interface"}


def test_scopes_every_code_node_to_repository() -> None:
    first = _map(100)
    second = _map(101)

    assert all(node.id.startswith("100:") for node in first.nodes)
    assert all(node.id.startswith("101:") for node in second.nodes)
    assert {node.id for node in first.nodes}.isdisjoint(node.id for node in second.nodes)


def test_deduplicates_shared_package_when_resolving_project() -> None:
    first = _map(100, "src/App.java")
    second = _map(100, "src/Other.java")

    resolved = resolve_cross_file_references((first, second))

    packages = [node for node in resolved.nodes if node.type == "Package"]
    assert len(packages) == 1


def test_class_fields_use_neo4j_compatible_primitive_values() -> None:
    result = JavaFileResult(
        "src/App.java",
        "com.example",
        (),
        (
            JavaClassResult(
                "App",
                "class",
                "Other",
                None,
                (),
                (),
                (FieldResult("repository", "OrderRepository"),),
                (),
            ),
        ),
    )

    class_node = next(
        node for node in map_java_file(100, result, "abc123").nodes if node.type == "Class"
    )

    assert class_node.properties["fields"] == ["OrderRepository repository"]


def test_method_versions_own_calls_and_link_to_logical_methods_and_commit() -> None:
    result = parse_java_file(
        "src/App.java",
        b"class App { void target() {} void source() { target(); } }",
    )

    document = resolve_cross_file_references((map_java_file(100, result, "abc123"),))
    methods = {node.properties["name"]: node for node in document.nodes if node.type == "Method"}
    versions = {
        node.properties["methodKey"]: node
        for node in document.nodes
        if node.type == "MethodVersion"
    }
    source_version = versions[methods["source"].id]

    assert any(
        edge.type == "HAS_VERSION"
        and edge.source == methods["source"].id
        and edge.target == source_version.id
        for edge in document.edges
    )
    assert any(
        edge.type == "INTRODUCED_IN"
        and edge.source == source_version.id
        and edge.target == "100:commit:abc123"
        for edge in document.edges
    )
    assert any(
        edge.type == "CALLS"
        and edge.source == source_version.id
        and edge.target == methods["target"].id
        for edge in document.edges
    )


def test_unchanged_method_reuses_version_and_changed_body_creates_new_version() -> None:
    before = parse_java_file("src/App.java", b"class App { void run() { start(); } }")
    moved = parse_java_file(
        "src/App.java", b"class App {\n\n  void run() { start(); }\n}"
    )
    changed = parse_java_file("src/App.java", b"class App { void run() { stop(); } }")

    def version_id(result):
        return next(
            node.id
            for node in map_java_file(100, result, "abc123").nodes
            if node.type == "MethodVersion"
        )

    assert version_id(before) == version_id(moved)
    assert version_id(before) != version_id(changed)
