"""Java parsing and mapping tests for semantic code identifiers."""

from app.graph.mappings import map_java_file
from app.parsers.languages.java import parse_java_file
from app.services.chunking import build_chunks_from_file


def _parse(source: str):
    return parse_java_file("src/main/java/com/example/Sample.java", source.encode())


def test_parser_builds_fqn_for_nested_classes_and_normalizes_signatures() -> None:
    result = _parse(
        """
        package com.example;
        class Outer {
            Outer(String... names) {}
            class Inner { void save(List < String > values, int [] ids) {} }
        }
        """
    )

    assert [item.qualified_name for item in result.classes] == [
        "com.example.Outer",
        "com.example.Outer.Inner",
    ]
    assert result.classes[0].methods[0].param_signature == "(String...)"
    assert result.classes[1].methods[0].param_signature == "(List<String>,int[])"


def test_declaration_reordering_keeps_class_and_method_ids() -> None:
    before = _parse(
        """
        package com.example;
        class First { void alpha() {} void stable(String value) {} }
        class Target { Target() {} void run(int value) {} }
        """
    )
    after = _parse(
        """
        package com.example;
        class Added { void newMethod() {} }
        class Target { void run(int value) {} Target() {} }
        class First { void stable(String value) {} void alpha() {} }
        """
    )

    before_ids = {node.id for node in map_java_file(100, before).nodes}
    after_ids = {node.id for node in map_java_file(100, after).nodes}

    stable_ids = {node_id for node_id in before_ids if "First" in node_id or "Target" in node_id}
    assert stable_ids <= after_ids


def test_overloads_nested_classes_and_repositories_do_not_collide() -> None:
    result = _parse(
        """
        package com.example;
        class A { class Inner { void save(String value) {} void save(int value) {} } }
        class B { class Inner { void save(String value) {} } }
        """
    )

    first_ids = {node.id for node in map_java_file(100, result).nodes}
    second_ids = {node.id for node in map_java_file(101, result).nodes}

    assert len(first_ids) == len(map_java_file(100, result).nodes)
    assert first_ids.isdisjoint(second_ids)


def test_graph_methods_and_chunks_share_exact_ids() -> None:
    result = _parse(
        """
        package com.example;
        class Sample { Sample(String value) {} void save() {} void save(int value) {} }
        """
    )
    document = map_java_file(100, result)
    chunks = build_chunks_from_file(100, result, "abc123")

    method_ids = {node.id for node in document.nodes if node.type == "Method"}
    assert method_ids == {chunk.graph_node_id for chunk in chunks}
