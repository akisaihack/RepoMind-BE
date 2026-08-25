"""Stable public evidence identifiers derived from internal graph identities."""

from hashlib import sha256


def evidence_id(evidence_type: str, internal_id: str) -> str:
    digest = sha256(internal_id.encode("utf-8")).hexdigest()[:16]
    return f"evidence:{evidence_type}:{digest}"


__all__ = ["evidence_id"]
