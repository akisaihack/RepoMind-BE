"""직접 호출 그래프의 MethodVersion을 PostgreSQL 코드 출처로 보강한다."""

import re
from collections import defaultdict
from collections.abc import Mapping

from app.ai.rag.state import QAState
from app.extensions import db
from app.repositories.code_chunk import CodeChunkRepository

MAX_ENRICHED_CODE_CONTEXTS = 4
_SIMPLE_GETTER_BODY = re.compile(r"\{\s*return\s+(?:this\.)?\w+;\s*\}\s*$", re.DOTALL)
_SIMPLE_SETTER_BODY = re.compile(
    r"\{\s*(?:this\.)?(?P<field>\w+)\s*=\s*(?P=field);\s*\}\s*$",
    re.DOTALL,
)


def enrich_code_evidence(state: QAState) -> dict:
    """선택 대상이 직접 호출하는 주요 내부 메서드의 코드 청크를 조회한다."""
    selected_target = state.get("selected_target") or {}
    selected_version_id = selected_target.get("graph_node_id")
    if not isinstance(selected_version_id, str):
        return {"enriched_code_results": []}

    graph_results = state.get("graph_results", {}) or {}
    edges = graph_results.get("edges", [])
    direct_method_ids = _direct_unambiguous_method_ids(edges, selected_version_id)
    version_ids = _single_version_ids(edges, direct_method_ids)
    if not version_ids:
        return {"enriched_code_results": []}

    chunks = CodeChunkRepository(db.session).find_by_graph_node_ids(
        state["github_repository_id"], version_ids
    )
    chunks_by_id = {chunk.graph_node_id: chunk for chunk in chunks}
    results = []
    for version_id in version_ids:
        chunk = chunks_by_id.get(version_id)
        if chunk is None or _is_trivial_method(chunk.method_name, chunk.text):
            continue
        results.append(_chunk_to_result(chunk))
        if len(results) >= MAX_ENRICHED_CODE_CONTEXTS:
            break
    return {"enriched_code_results": results}


def _direct_unambiguous_method_ids(edges: list[dict], selected_version_id: str) -> list[str]:
    method_ids: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        if edge.get("type") != "CALLS" or edge.get("source") != selected_version_id:
            continue
        metadata = edge.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("ambiguous") is True:
            continue
        target = edge.get("target")
        if isinstance(target, str) and target not in seen:
            seen.add(target)
            method_ids.append(target)
    return method_ids


def _single_version_ids(edges: list[dict], method_ids: list[str]) -> list[str]:
    method_id_set = set(method_ids)
    versions_by_method: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if (
            edge.get("type") == "HAS_VERSION"
            and source in method_id_set
            and isinstance(target, str)
        ):
            versions_by_method[source].append(target)
    return [
        versions[0]
        for method_id in method_ids
        if len(versions := versions_by_method[method_id]) == 1
    ]


def _is_trivial_method(method_name: str | None, source_code: str) -> bool:
    if not method_name:
        return True
    if method_name.startswith(("get", "is")):
        return _SIMPLE_GETTER_BODY.search(source_code) is not None
    if method_name.startswith("set"):
        return _SIMPLE_SETTER_BODY.search(source_code) is not None
    return False


def _chunk_to_result(chunk) -> dict:
    return {
        "graph_node_id": chunk.graph_node_id,
        "method_node_id": chunk.method_node_id,
        "text": chunk.text,
        "similarity": 1.0,
        "path": chunk.path,
        "class_name": chunk.class_name,
        "method_name": chunk.method_name,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "api_http_method": chunk.api_http_method,
        "api_path": chunk.api_path,
        "commit_hash": chunk.commit_hash,
    }
