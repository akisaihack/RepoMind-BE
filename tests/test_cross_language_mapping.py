"""app/graph/mappings.py 테스트 — 특히 크로스 언어 이름 충돌 회귀 테스트.

이 테스트가 가장 우선순위 높음(구현 계획 문서 §검증 방법 2번 참고): Java/
JavaScript/Python이 같은 프로젝트에 섞이면, resolve_cross_file_references()의
이름 인덱스가 언어를 구분하지 않을 경우 세 언어의 save()가 서로 잘못
이어질 수 있음. (language, name) 튜플로 인덱스 키를 바꾼 수정이 이 문제를
실제로 막는지 확인한다.
"""

from app.graph.mappings import (
    map_java_file,
    map_javascript_file,
    map_python_file,
    resolve_cross_file_references,
)
from app.parsers.languages.java import parse_java_file
from app.parsers.languages.javascript import parse_javascript_file
from app.parsers.languages.python import parse_python_file

JAVA_SRC = b"""
package com.example;

public class PollService {
    public Poll save(Poll poll) {
        return poll;
    }
}
"""

# JS/Python 쪽에도 이름이 우연히 겹치는 save()를 최상위(module) 함수로 하나씩
# 둠 — 리시버 없이 부르기 때문에 후보가 여러 개면 세 언어 다 걸림.
JS_SRC = b"""
export function save(item) {
    return item;
}

export function persist(item) {
    return save(item);
}
"""

PYTHON_SRC = b"""
def save(item):
    return item


def persist(item):
    return save(item)
"""


def _merged_document():
    java_result = parse_java_file("PollService.java", JAVA_SRC)
    js_result = parse_javascript_file("store.js", JS_SRC)
    python_result = parse_python_file("store.py", PYTHON_SRC)
    java_doc = map_java_file(1, java_result, "commit1")
    js_doc = map_javascript_file(1, js_result, "commit1")
    python_doc = map_python_file(1, python_result, "commit1")
    return resolve_cross_file_references([java_doc, js_doc, python_doc])


def _persist_call_target(document, language: str):
    """주어진 언어의 persist() 메서드가 실제로 어느 save()로 이어졌는지 찾음."""
    nodes_by_id = {node.id: node for node in document.nodes}
    persist_method = next(
        n
        for n in document.nodes
        if n.type == "Method"
        and n.properties.get("name") == "persist"
        and n.properties.get("language") == language
    )
    # CALLS의 source는 Method가 아니라 MethodVersion 노드이므로, persist
    # 메서드에 대응하는 버전 노드를 HAS_VERSION 엣지로 먼저 찾아야 함.
    persist_version_ids = {
        edge.target
        for edge in document.edges
        if edge.type == "HAS_VERSION" and edge.source == persist_method.id
    }
    assert persist_version_ids, f"{language} persist 메서드의 MethodVersion을 못 찾음(테스트 전제 깨짐)"

    persist_calls = [
        edge
        for edge in document.edges
        if edge.type == "CALLS" and edge.source in persist_version_ids
    ]
    assert len(persist_calls) == 1
    return persist_calls[0], nodes_by_id[persist_calls[0].target]


def test_javascript_save_call_stays_within_javascript():
    document = _merged_document()
    call_edge, target_node = _persist_call_target(document, "javascript")

    # JS의 save() 호출은 반드시 JS의 save 함수로 이어져야 하고, Java/Python의
    # save로는 절대 이어지면 안 됨 (수정 전에는 이게 실패했음).
    assert target_node.properties.get("language") == "javascript"
    assert target_node.properties.get("class_name") == "store$module"
    assert call_edge.properties.get("ambiguous") is not True
    assert call_edge.properties.get("external") is not True


def test_python_save_call_stays_within_python():
    document = _merged_document()
    call_edge, target_node = _persist_call_target(document, "python")

    assert target_node.properties.get("language") == "python"
    assert target_node.properties.get("class_name") == "store$module"
    assert call_edge.properties.get("ambiguous") is not True
    assert call_edge.properties.get("external") is not True


def test_java_save_is_unaffected_by_other_languages_save_existing():
    document = _merged_document()

    java_method_nodes = [
        n
        for n in document.nodes
        if n.type == "Method" and n.properties.get("class_name") == "PollService"
    ]
    assert len(java_method_nodes) == 1
    assert java_method_nodes[0].properties.get("language") == "java"
