"""검색 후보에서 사용자에게 표시할 검증 가능한 답변 근거를 구성한다."""

import re
from collections.abc import Mapping

from app.ai.rag.evidence_ids import evidence_id
from app.ai.rag.state import QAState, VectorHit
from app.dtos.question import QuestionKind

_METHOD_KEY_PATTERN = re.compile(
    r"^\d+:(?:class|interface):(?P<path>.+?\.java):(?P<owner>[^:]+):"
    r"(?:method|constructor):(?P<method>[^:]+):(?P<signature>\(.*\))$"
)
_EMBEDDING_METADATA_PREFIXES = ("// package:", "// class:", "// method:")
_FULL_CODE_REQUEST_PATTERN = re.compile(
    r"(?:전체\s*(?:코드|구현|메서드)|메서드\s*전체|원문|full(?:\s+\w+){0,3}\s+(?:code|method))",
    re.IGNORECASE,
)
_QUERY_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_MAX_EXCERPT_LINES = 30
_MAX_EVIDENCE_BY_QUESTION_KIND = {
    QuestionKind.FLOW: 5,
    QuestionKind.IMPACT: 5,
    QuestionKind.INTENT: 8,
    QuestionKind.LOCATION: 5,
}
_QUESTION_KEYWORD_PATTERNS = {
    "login": re.compile(r"로그인|인증|토큰"),
    "request": re.compile(r"요청|엔드포인트|api|url|진입"),
    "save": re.compile(r"저장|등록|생성|업데이트|삭제"),
    "analysis": re.compile(r"분석|파싱|청킹|임베딩"),
    "condition": re.compile(r"조건|검증|여부|가능|실패|예외"),
}
_CODE_PATTERNS_BY_QUESTION_KEYWORD = {
    "login": re.compile(r"login|auth|token|credential", re.IGNORECASE),
    "request": re.compile(r"request|route|endpoint|handle|controller", re.IGNORECASE),
    "save": re.compile(r"save|store|upsert|persist|delete|update|create", re.IGNORECASE),
    "analysis": re.compile(r"parse|chunk|embed|analy[sz]e", re.IGNORECASE),
    "condition": re.compile(r"\bif\b|\bvalidate|\bcheck|\braise\b|\bthrow\b", re.IGNORECASE),
}


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
            evidence.append(_vector_evidence(hit, state["question"]))

    evidence.extend(
        _vector_evidence(hit, state["question"])
        for hit in state.get("enriched_code_results", [])
    )

    if question_kind is QuestionKind.INTENT:
        evidence.extend(
            _history_evidence(
                graph_nodes,
                graph_results.get("edges", []),
                state["question"],
            )
        )

    deduplicated = _deduplicate(evidence)
    return {"evidence": deduplicated[:_MAX_EVIDENCE_BY_QUESTION_KIND[question_kind]]}


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


def _vector_evidence(hit: VectorHit, question: str) -> dict:
    path = hit.get("path", "")
    title = _symbol_name(
        hit.get("class_name"),
        hit.get("method_name"),
        hit.get("param_signature"),
        path,
    )
    return _code_evidence(
        internal_id=hit["graph_node_id"],
        title=title,
        path=path,
        source_code=hit.get("text"),
        start_line=hit.get("start_line"),
        end_line=hit.get("end_line"),
        question=question,
    )


def _code_evidence(
    *,
    internal_id: str,
    title: str,
    path: str,
    source_code: object,
    start_line: object,
    end_line: object,
    question: str,
) -> dict:
    excerpt = _excerpt_from(source_code, start_line, question)
    location = _code_location(path, excerpt["excerptStartLine"], excerpt["excerptEndLine"])
    return {
        "id": evidence_id("code", internal_id),
        "type": "code",
        "title": title,
        "location": location,
        "description": f"{title} · {location}" if location else title,
        "excerpt": excerpt["text"],
        "fullExcerpt": excerpt["fullText"],
        "startLine": _optional_line(start_line),
        "endLine": _optional_line(end_line),
        "excerptStartLine": excerpt["excerptStartLine"],
        "excerptEndLine": excerpt["excerptEndLine"],
        "hasMoreBefore": excerpt["hasMoreBefore"],
        "hasMoreAfter": excerpt["hasMoreAfter"],
    }


def _history_evidence(
    nodes: list[dict], edges: list[dict], question: str
) -> list[dict]:
    evidence: list[dict] = []
    issue_relations = _issue_relations(edges)
    for node in nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        node_type = metadata.get("node_type")
        if node_type == "MethodVersion":
            item = _method_version_evidence(node, metadata, question)
        elif node_type == "Commit":
            item = _commit_evidence(node, metadata)
        elif node_type == "PullRequest":
            item = _work_item_evidence(node, metadata, "Pull Request")
        elif node_type == "Issue":
            item = _work_item_evidence(
                node,
                metadata,
                "Issue",
                relation=issue_relations.get(node.get("id")),
            )
        else:
            item = None
        if item is not None:
            evidence.append(item)
    return evidence


def _issue_relations(edges: list[dict]) -> dict[object, str]:
    relations: dict[object, str] = {}
    for edge in edges:
        relation = edge.get("type")
        target = edge.get("target")
        if relation not in {"RESOLVES", "REFERENCES"}:
            continue
        if relations.get(target) != "RESOLVES":
            relations[target] = relation
    return relations


def _method_version_evidence(
    node: dict, metadata: Mapping, question: str
) -> dict | None:
    method_key = metadata.get("method_key")
    source_code = metadata.get("source_code")
    if not isinstance(method_key, str) or not isinstance(source_code, str):
        return None
    parsed = _parse_method_key(method_key)
    title = parsed[1] if parsed else "코드 변경 버전"
    path = parsed[0] if parsed else ""
    return _code_evidence(
        internal_id=node["id"],
        title=title,
        path=path,
        source_code=source_code,
        start_line=metadata.get("start_line"),
        end_line=metadata.get("end_line"),
        question=question,
    )


def _commit_evidence(node: dict, metadata: Mapping) -> dict | None:
    sha = metadata.get("sha")
    if not isinstance(sha, str) or not sha:
        return None
    message = metadata.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    title = message.strip()
    details = [metadata.get("author"), metadata.get("committed_at")]
    description = " · ".join(value for value in details if isinstance(value, str) and value)
    return {
        "id": evidence_id("commit", node["id"]),
        "type": "commit",
        "title": title,
        "location": sha,
        "description": description or title,
        "excerpt": None,
    }


def _work_item_evidence(
    node: dict,
    metadata: Mapping,
    item_type: str,
    *,
    relation: str | None = None,
) -> dict | None:
    number = metadata.get("number")
    title = metadata.get("title")
    if not isinstance(number, int) or not isinstance(title, str) or not title.strip():
        return None
    body = metadata.get("body")
    excerpt = body.strip() if isinstance(body, str) and body.strip() else None
    relation_label = {
        "RESOLVES": "해결한 이슈",
        "REFERENCES": "참조한 이슈",
    }.get(relation)
    state = metadata.get("state")
    details = [relation_label, state if isinstance(state, str) else None]
    description = " · ".join(value for value in details if value)
    return {
        "id": evidence_id("itsm", node["id"]),
        "type": "itsm",
        "title": f"{item_type} #{number}: {title.strip()}",
        "location": metadata.get("url") if isinstance(metadata.get("url"), str) else "",
        "description": description or excerpt or title.strip(),
        "excerpt": excerpt,
        "fullExcerpt": excerpt,
    }


def _parse_method_key(method_key: str) -> tuple[str, str] | None:
    match = _METHOD_KEY_PATTERN.match(method_key)
    if match is None:
        return None
    class_name = match.group("owner").rsplit(".", 1)[-1]
    symbol = f"{class_name}.{match.group('method')}{match.group('signature')}"
    return match.group("path"), symbol


def _symbol_name(
    class_name: object,
    method_name: object,
    param_signature: object,
    path: str,
) -> str:
    parts = [value for value in (class_name, method_name) if isinstance(value, str) and value]
    symbol = ".".join(parts)
    if symbol and isinstance(param_signature, str) and param_signature:
        return f"{symbol}{param_signature}"
    return symbol or path


def _excerpt_from(source_code: object, start_line: object, question: str) -> dict:
    source_lines = _source_lines(source_code)
    source_start_line = _optional_line(start_line)
    if not source_lines:
        return {
            "text": None,
            "fullText": None,
            "excerptStartLine": source_start_line,
            "excerptEndLine": source_start_line,
            "hasMoreBefore": False,
            "hasMoreAfter": False,
        }

    if len(source_lines) <= _MAX_EXCERPT_LINES or _requests_full_code(question):
        return _excerpt_result(
            source_lines, 0, source_start_line, excerpt_length=len(source_lines)
        )

    excerpt_start = _relevant_line_index(source_lines, question)
    excerpt_start = min(excerpt_start, len(source_lines) - _MAX_EXCERPT_LINES)
    return _excerpt_result(source_lines, excerpt_start, source_start_line)


def _source_lines(source_code: object) -> list[str]:
    if not isinstance(source_code, str):
        return []
    lines = source_code.splitlines()
    while lines and lines[0].startswith(_EMBEDDING_METADATA_PREFIXES):
        lines.pop(0)
    return lines


def _relevant_line_index(source_lines: list[str], question: str) -> int:
    """질문 속 식별어·의도어와 일치하는 실제 코드 행을 발췌 기준으로 잡는다."""
    tokens = {token.lower() for token in _QUERY_TOKEN_PATTERN.findall(question)}
    if tokens:
        for index, line in enumerate(source_lines):
            lowered = line.lower()
            if any(token in lowered for token in tokens):
                return max(0, index - 10)

    for keyword, question_pattern in _QUESTION_KEYWORD_PATTERNS.items():
        if not question_pattern.search(question):
            continue
        code_pattern = _CODE_PATTERNS_BY_QUESTION_KEYWORD[keyword]
        for index, line in enumerate(source_lines):
            if code_pattern.search(line):
                return max(0, index - 10)

    for index, line in enumerate(source_lines):
        if re.search(r"\b(?:return|raise|throw)\b|\w+\s*\(", line):
            return max(0, index - 10)
    return 0


def _excerpt_result(
    source_lines: list[str],
    excerpt_start: int,
    source_start_line: int | None,
    *,
    excerpt_length: int = _MAX_EXCERPT_LINES,
) -> dict:
    excerpt_lines = source_lines[excerpt_start : excerpt_start + excerpt_length]
    excerpt_end = excerpt_start + len(excerpt_lines)
    excerpt_start_line = (
        source_start_line + excerpt_start if source_start_line is not None else None
    )
    excerpt_end_line = (
        source_start_line + excerpt_end - 1 if source_start_line is not None else None
    )
    return {
        "text": "\n".join(excerpt_lines),
        "fullText": "\n".join(source_lines),
        "excerptStartLine": excerpt_start_line,
        "excerptEndLine": excerpt_end_line,
        "hasMoreBefore": excerpt_start > 0,
        "hasMoreAfter": excerpt_end < len(source_lines),
    }


def _requests_full_code(question: str) -> bool:
    return _FULL_CODE_REQUEST_PATTERN.search(question) is not None


def _optional_line(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


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
