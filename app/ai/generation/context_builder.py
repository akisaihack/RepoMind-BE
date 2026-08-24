"""Build a compact LLM context without changing visualization graph data."""

import json
import logging
from collections.abc import Mapping
from typing import Any

from app.dtos.answer_context import (
    AnswerCodeContext,
    AnswerEvidenceContext,
    AnswerGenerationContext,
    AnswerRelationContext,
)
from app.dtos.response_generation import QueryIntent, ResponseGenerationInput

logger = logging.getLogger(__name__)

FALLBACK_MAX_CONTEXT_CHARS = 20_000
MIN_FALLBACK_CONTEXT_CHARS = 4_000

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
    """Remove transport-only data, limiting size only for a provider retry."""

    def __init__(
        self,
        *,
        fallback_max_context_chars: int = FALLBACK_MAX_CONTEXT_CHARS,
    ) -> None:
        if fallback_max_context_chars < 1_000:
            raise ValueError("Fallback LLM context limit must be at least 1,000 characters.")
        self._fallback_max_context_chars = fallback_max_context_chars

    def build(
        self,
        input_data: ResponseGenerationInput,
        *,
        max_context_chars: int | None = None,
    ) -> AnswerGenerationContext:
        """Compact all relevant evidence and optionally fit it to a retry budget."""
        if max_context_chars is not None and max_context_chars < 1_000:
            raise ValueError("LLM context limit must be at least 1,000 characters.")

        code = self._compact_code(input_data.context.code)
        relations = self._compact_relations(
            input_data.context.graph,
            input_data.intent,
        )
        history = self._compact_history(input_data.context.history)
        evidence = self._compact_evidence(input_data.context.evidence)

        context = AnswerGenerationContext(
            code=code,
            relations=relations,
            history=history,
            evidence=evidence,
        )
        if max_context_chars is not None:
            context = self._fit_budget(input_data.intent, context, max_context_chars)
        logger.info(
            "Prepared LLM context: intent=%s code=%d relations=%d history=%d chars=%d limited=%s",
            input_data.intent.value,
            len(context.code),
            len(context.relations),
            len(context.history),
            _context_size(context),
            max_context_chars is not None,
        )
        return context

    def build_fallback(
        self,
        input_data: ResponseGenerationInput,
        original_size: int,
    ) -> AnswerGenerationContext:
        """Build a smaller context after a provider rate/context limit response."""
        budget = min(
            self._fallback_max_context_chars,
            max(MIN_FALLBACK_CONTEXT_CHARS, original_size // 2),
        )
        return self.build(input_data, max_context_chars=budget)

    @staticmethod
    def size(context: AnswerGenerationContext) -> int:
        return _context_size(context)

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
    def _compact_evidence(rows: list[dict[str, Any]]) -> list[AnswerEvidenceContext]:
        compact: list[AnswerEvidenceContext] = []
        seen: set[str] = set()
        for row in rows:
            evidence_id = _optional_string(row.get("id"))
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            compact.append(
                AnswerEvidenceContext(
                    id=evidence_id,
                    type=_optional_string(row.get("type")) or "code",
                    title=_optional_string(row.get("title")) or "",
                    location=_optional_string(row.get("location")) or "",
                    description=_optional_string(row.get("description")) or "",
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
        context: AnswerGenerationContext,
        max_context_chars: int,
    ) -> AnswerGenerationContext:
        while _context_size(context) > max_context_chars:
            if intent is QueryIntent.HISTORY:
                reduced = (
                    _remove_last(context.relations)
                    or _remove_last(context.code)
                    or _remove_last(context.evidence, keep=1)
                )
            else:
                reduced = (
                    _remove_last(context.history)
                    or _remove_last(context.evidence, keep=1)
                    or _remove_last(context.relations)
                    or _remove_last(context.code, keep=1)
                )
            if not reduced:
                break
        _truncate_last_code(context, max_context_chars)
        _truncate_last_history(context, max_context_chars)
        return context


def _remove_last(collection: list[Any], *, keep: int = 0) -> bool:
    if len(collection) <= keep:
        return False
    collection.pop()
    return True


def _truncate_last_code(context: AnswerGenerationContext, max_chars: int) -> None:
    if _context_size(context) <= max_chars or not context.code:
        return
    item = context.code[-1]
    overage = _context_size(context) - max_chars
    keep = max(0, len(item.code) - overage - 20)
    item.code = f"{item.code[:keep]}…" if keep else ""


def _truncate_last_history(context: AnswerGenerationContext, max_chars: int) -> None:
    if _context_size(context) <= max_chars or not context.history:
        return
    item = context.history[-1]
    for key, value in reversed(item.items()):
        if not isinstance(value, str):
            continue
        overage = _context_size(context) - max_chars
        keep = max(0, len(value) - overage - 20)
        item[key] = f"{value[:keep]}…" if keep else ""
        if _context_size(context) <= max_chars:
            return


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
