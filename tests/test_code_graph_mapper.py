"""Repository-scoped Java code graph mapping tests."""

from app.dtos.analysis import JavaClassResult, JavaFileResult, JavaMethodResult
from app.graph.mappings import map_java_file, resolve_cross_file_references


def _map(repository_id: int, path: str = "src/App.java"):
    method = JavaMethodResult("name", "", False, 1, 1, "", None, ())
    classes = (
        JavaClassResult("Named", "interface", "Other", None, (), (), (), (method,)),
        JavaClassResult("App", "class", "Other", None, (), ("Named",), (), (method,)),
    )
    result = JavaFileResult(path, "com.example", (), classes)
    return map_java_file(repository_id, result)


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
