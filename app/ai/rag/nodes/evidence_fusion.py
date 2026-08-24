"""검색 후보에서 사용자에게 표시할 검증 가능한 답변 근거를 구성한다."""

import re
from collections.abc import Mapping
from hashlib import sha256

from app.ai.rag.state import QAState, VectorHit
from app.dtos.question import QuestionKind

_METHOD_KEY_PATTERN = re.compile(
    r"^\d+:(?:class|interface):(?P<path>.+?\.java):(?P<owner>[^:]+):"
    r"(?:method|constructor):(?P<method>[^:]+):(?P<signature>\(.*\))$"
)


def fuse_evidence(state: QAState) -> dict:
    """검색용 후보와 사용자에게 표시할 출처를 분리해 반환한다."""
    graph_results = state.get("graph_results", {}) or {}
    graph_nodes = graph_results.get("nodes", [])
    graph_node_ids = {
        node.get("id") for node in graph_nodes if isinstance(node.get("id"), str)
    }
    selected_target = state.get("selected_target") or {}
    question_kind = QuestionKind(state.get("question_kind", QuestionKind.LOCATION))

    evidence: list[dict] = []
    for hit in state.get("vector_results", []):
        if _is_user_evidence_candidate(hit, selected_target, graph_node_ids):
            evidence.append(_vector_evidence(hit))

    evidence.extend(
        _vector_evidence(hit) for hit in state.get("enriched_code_results", [])
    )

    if question_kind is QuestionKind.INTENT:
        evidence.extend(_history_evidence(graph_nodes))

    return {"evidence": _deduplicate(evidence)}


def _is_user_evidence_candidate(
    hit: VectorHit,
    selected_target: Mapping,
    graph_node_ids: set[str],
) -> bool:
    hit_ids = {
        value
        for value in (hit.get("graph_node_id"), hit.get("method_node_id"))
        if isinstance(value, str)
    }
    selected_ids = {
        value
        for value in (
            selected_target.get("graph_node_id"),
            selected_target.get("method_node_id"),
        )
        if isinstance(value, str)
    }
    return bool((hit_ids & selected_ids) or (hit_ids & graph_node_ids))


def _vector_evidence(hit: VectorHit) -> dict:
    path = hit.get("path", "")
    location = _code_location(path, hit.get("start_line"), hit.get("end_line"))
    title = _symbol_name(hit.get("class_name"), hit.get("method_name"), path)
    return {
        "id": _evidence_id("code", hit["graph_node_id"]),
        "type": "code",
        "title": title,
        "location": location,
        "description": f"{title} · {location}" if location else title,
        "excerpt": hit.get("text"),
    }


def _history_evidence(nodes: list[dict]) -> list[dict]:
    evidence: list[dict] = []
    for node in nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        node_type = metadata.get("node_type")
        if node_type == "MethodVersion":
            item = _method_version_evidence(node, metadata)
        elif node_type == "Commit":
            item = _commit_evidence(node, metadata)
        else:
            item = None
        if item is not None:
            evidence.append(item)
    return evidence


def _method_version_evidence(node: dict, metadata: Mapping) -> dict | None:
    method_key = metadata.get("method_key")
    source_code = metadata.get("source_code")
    if not isinstance(method_key, str) or not isinstance(source_code, str):
        return None
    parsed = _parse_method_key(method_key)
    title = parsed[1] if parsed else "코드 변경 버전"
    path = parsed[0] if parsed else ""
    location = _code_location(path, metadata.get("start_line"), metadata.get("end_line"))
    return {
        "id": _evidence_id("code", node["id"]),
        "type": "code",
        "title": title,
        "location": location,
        "description": f"{title} · {location}" if location else title,
        "excerpt": source_code,
    }


def _commit_evidence(node: dict, metadata: Mapping) -> dict | None:
    sha = metadata.get("sha")
    if not isinstance(sha, str) or not sha:
        return None
    message = metadata.get("message")
    title = message if isinstance(message, str) and message else f"커밋 {sha[:8]}"
    details = [metadata.get("author"), metadata.get("committed_at")]
    description = " · ".join(value for value in details if isinstance(value, str) and value)
    return {
        "id": _evidence_id("commit", node["id"]),
        "type": "commit",
        "title": title,
        "location": sha,
        "description": description or title,
        "excerpt": None,
    }


def _parse_method_key(method_key: str) -> tuple[str, str] | None:
    match = _METHOD_KEY_PATTERN.match(method_key)
    if match is None:
        return None
    class_name = match.group("owner").rsplit(".", 1)[-1]
    symbol = f"{class_name}.{match.group('method')}{match.group('signature')}"
    return match.group("path"), symbol


def _symbol_name(class_name: object, method_name: object, path: str) -> str:
    parts = [value for value in (class_name, method_name) if isinstance(value, str) and value]
    return ".".join(parts) or path


def _code_location(path: str, start_line: object, end_line: object) -> str:
    if isinstance(start_line, int) and isinstance(end_line, int):
        line_range = (
            f"Line {start_line}" if start_line == end_line else f"Line {start_line}–{end_line}"
        )
        return f"{path} · {line_range}" if path else line_range
    return path


def _deduplicate(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduplicated: list[dict] = []
    for item in items:
        item_id = item["id"]
        if item_id in seen:
            continue
        seen.add(item_id)
        deduplicated.append(item)
    return deduplicated


def _evidence_id(evidence_type: str, internal_id: str) -> str:
    digest = sha256(internal_id.encode("utf-8")).hexdigest()[:16]
    return f"evidence:{evidence_type}:{digest}"
