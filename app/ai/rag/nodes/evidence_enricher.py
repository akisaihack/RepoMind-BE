"""호출 그래프를 BFS로 순회해 MethodVersion의 코드 출처를 보강한다."""

import re
from collections import defaultdict, deque
from collections.abc import Mapping

from app.ai.rag.state import QAState
from app.extensions import db
from app.graph.queries.traversal import DEFAULT_CALLS_DEPTH
from app.repositories.code_chunk import CodeChunkRepository

MAX_CALL_DEPTH = DEFAULT_CALLS_DEPTH
MAX_ENRICHED_CODE_CONTEXTS = 20
_SIMPLE_GETTER_BODY = re.compile(r"\{\s*return\s+(?:this\.)?\w+;\s*\}\s*$", re.DOTALL)
_SIMPLE_SETTER_BODY = re.compile(
    r"\{\s*(?:this\.)?(?P<field>\w+)\s*=\s*(?P=field);\s*\}\s*$",
    re.DOTALL,
)


def enrich_code_evidence(state: QAState) -> dict:
    """선택 대상부터 최대 5단계의 주요 내부 호출 코드 청크를 조회한다."""
    selected_target = state.get("selected_target") or {}
    selected_version_id = selected_target.get("graph_node_id")
    if not isinstance(selected_version_id, str):
        return {"enriched_code_results": []}

    graph_results = state.get("graph_results", {}) or {}
    edges = graph_results.get("edges", [])
    version_ids = _bfs_version_ids(edges, selected_version_id)
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


def _bfs_version_ids(
    edges: list[dict],
    selected_version_id: str,
    max_depth: int = MAX_CALL_DEPTH,
) -> list[str]:
    """CALLS→HAS_VERSION을 한 단계로 보고 버전 노드를 BFS 순서로 반환한다."""
    called_methods_by_version: dict[str, list[str]] = defaultdict(list)
    versions_by_method: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        edge_type = edge.get("type")
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if edge_type == "CALLS":
            metadata = edge.get("metadata")
            if isinstance(metadata, Mapping) and metadata.get("ambiguous") is True:
                continue
            if target not in called_methods_by_version[source]:
                called_methods_by_version[source].append(target)
        elif edge_type == "HAS_VERSION":
            versions_by_method[source].append(target)

    queue = deque([(selected_version_id, 0)])
    visited_versions = {selected_version_id}
    visited_methods: set[str] = set()
    ordered_version_ids: list[str] = []

    while queue:
        version_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for method_id in called_methods_by_version[version_id]:
            if method_id in visited_methods:
                continue
            visited_methods.add(method_id)
            versions = versions_by_method[method_id]
            if len(versions) != 1:
                continue
            next_version_id = versions[0]
            if next_version_id in visited_versions:
                continue
            visited_versions.add(next_version_id)
            ordered_version_ids.append(next_version_id)
            queue.append((next_version_id, depth + 1))

    return ordered_version_ids


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
        # Historical chunk rows created before signature extraction do not
        # have this column populated. Keep them usable as evidence.
        "param_signature": getattr(chunk, "param_signature", ""),
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "api_http_method": chunk.api_http_method,
        "api_path": chunk.api_path,
        "commit_hash": chunk.commit_hash,
    }
