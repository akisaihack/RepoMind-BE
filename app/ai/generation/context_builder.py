"""Build a compact LLM context without changing visualization graph data."""

import json
import logging
from collections.abc import Mapping
from typing import Any

from app.dtos.answer_context import (
    AnswerCodeContext,
    AnswerGenerationContext,
    AnswerRelationContext,
)
from app.dtos.response_generation import QueryIntent, ResponseGenerationInput

logger = logging.getLogger(__name__)

MAX_CODE_CONTEXTS = 5
MAX_GRAPH_RELATIONS = 30
MAX_HISTORY_CONTEXTS = 10
MAX_CONTEXT_CHARS = 20_000

_RELATIONS_BY_INTENT = {
    QueryIntent.FLOW: frozenset({"CALLS"}),
    QueryIntent.DEPENDENCY: frozenset({"CALLS", "IMPLEMENTS", "EXTENDS", "IMPORTS"}),
    QueryIntent.HISTORY: frozenset(
        {"INTRODUCED_IN", "DELETED_IN", "CHANGED_BY", "MANAGES"}
    ),
    QueryIntent.EXPLANATION: frozenset(
        {"CALLS", "DECLARES", "CONTAINS", "IMPLEMENTS", "EXTENDS", "EXPOSES"}
    ),
}

_HISTORY_FIELDS = (
    "sha",
    "message",
    "title",
    "author",
    "date",
    "created_at",
    "path",
    "status",
    "additions",
    "deletions",
    "changes",
)


class LLMContextBuilder:
    """Remove transport-only graph data and enforce a final provider budget."""

    def __init__(
        self,
        *,
        max_code_contexts: int = MAX_CODE_CONTEXTS,
        max_graph_relations: int = MAX_GRAPH_RELATIONS,
        max_history_contexts: int = MAX_HISTORY_CONTEXTS,
        max_context_chars: int = MAX_CONTEXT_CHARS,
    ) -> None:
        limits = (max_code_contexts, max_graph_relations, max_history_contexts)
        if any(limit <= 0 for limit in limits) or max_context_chars < 1_000:
            raise ValueError("LLM context limits must be positive.")
        self._max_code_contexts = max_code_contexts
        self._max_graph_relations = max_graph_relations
        self._max_history_contexts = max_history_contexts
        self._max_context_chars = max_context_chars

    def build(self, input_data: ResponseGenerationInput) -> AnswerGenerationContext:
        code = self._compact_code(input_data.context.code)[: self._max_code_contexts]
        relations = self._compact_relations(
            input_data.context.graph,
            input_data.intent,
        )[: self._max_graph_relations]
        history = self._compact_history(input_data.context.history)[: self._max_history_contexts]

        context = self._fit_budget(input_data.intent, code, relations, history)
        logger.info(
            "Prepared LLM context: intent=%s code=%d relations=%d history=%d chars=%d",
            input_data.intent.value,
            len(context.code),
            len(context.relations),
            len(context.history),
            _context_size(context),
        )
        return context

    @staticmethod
    def _compact_code(rows: list[dict[str, Any]]) -> list[AnswerCodeContext]:
        compact: list[AnswerCodeContext] = []
        seen: set[tuple[str | None, str | None]] = set()
        for row in rows:
            code = row.get("text")
            if not isinstance(code, str) or not code.strip():
                continue
            class_name = _optional_string(row.get("class_name"))
            method_name = _optional_string(row.get("method_name"))
            symbol = ".".join(value for value in (class_name, method_name) if value) or None
            path = _optional_string(row.get("path"))
            identity = (path, symbol)
            if identity in seen:
                continue
            seen.add(identity)
            similarity = row.get("similarity")
            compact.append(
                AnswerCodeContext(
                    path=path,
                    symbol=symbol,
                    similarity=float(similarity) if isinstance(similarity, int | float) else None,
                    code=code.strip(),
                )
            )
        return compact

    @staticmethod
    def _compact_relations(
        rows: list[dict[str, Any]],
        intent: QueryIntent,
    ) -> list[AnswerRelationContext]:
        allowed = _RELATIONS_BY_INTENT[intent]
        compact: list[AnswerRelationContext] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            relation = row.get("relation")
            source = row.get("source")
            target = row.get("target")
            if relation not in allowed:
                continue
            if not isinstance(source, Mapping) or not isinstance(target, Mapping):
                continue
            source_name = _node_name(source)
            target_name = _node_name(target)
            if not source_name or not target_name:
                continue
            identity = (source_name, relation, target_name)
            if identity in seen:
                continue
            seen.add(identity)
            compact.append(
                AnswerRelationContext(
                    source=source_name,
                    relation=relation,
                    target=target_name,
                )
            )
        return compact

    @staticmethod
    def _compact_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            item = {key: row[key] for key in _HISTORY_FIELDS if row.get(key) is not None}
            if not item:
                name = _optional_string(row.get("name") or row.get("label"))
                if name:
                    item = {"summary": name}
            if not item:
                continue
            identity = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if identity in seen:
                continue
            seen.add(identity)
            compact.append(item)
        return compact

    def _fit_budget(
        self,
        intent: QueryIntent,
        code: list[AnswerCodeContext],
        relations: list[AnswerRelationContext],
        history: list[dict[str, Any]],
    ) -> AnswerGenerationContext:
        context = AnswerGenerationContext(code=code, relations=relations, history=history)
        while _context_size(context) > self._max_context_chars:
            if intent is QueryIntent.HISTORY:
                reduced = _remove_last(context.relations, context.code)
            else:
                reduced = _remove_last(context.history, context.relations, context.code)
            if not reduced:
                break
        _truncate_last_code(context, self._max_context_chars)
        return context


def _remove_last(*collections: list[Any]) -> bool:
    for collection in collections:
        if collection:
            collection.pop()
            return True
    return False


def _truncate_last_code(context: AnswerGenerationContext, max_chars: int) -> None:
    if _context_size(context) <= max_chars or not context.code:
        return
    item = context.code[-1]
    overage = _context_size(context) - max_chars
    keep = max(0, len(item.code) - overage - 20)
    item.code = f"{item.code[:keep]}…" if keep else ""


def _context_size(context: AnswerGenerationContext) -> int:
    return len(context.model_dump_json(exclude_none=True))


def _node_name(node: Mapping[str, Any]) -> str | None:
    name = _optional_string(node.get("name"))
    if name and not name.startswith("코드 버전"):
        return name

    metadata = node.get("metadata")
    detail = metadata.get("detail") if isinstance(metadata, Mapping) else None
    if isinstance(detail, str):
        parsed = _symbol_from_graph_key(detail)
        if parsed:
            return parsed
    return name


def _symbol_from_graph_key(value: str) -> str | None:
    marker = ":method:"
    if marker not in value:
        return None
    owner, method = value.split(marker, 1)
    class_name = owner.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
    method_name, separator, signature = method.partition(":")
    if not class_name or not method_name:
        return None
    return f"{class_name}.{method_name}{signature if separator else ''}"


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["LLMContextBuilder"]
