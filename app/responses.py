"""Shared API response helpers."""

from http import HTTPStatus
from typing import Any

from flask import Response, jsonify


def success_response(
    data: Any = None,
    *,
    status: HTTPStatus | int = HTTPStatus.OK,
) -> tuple[Response, int]:
    """Return a successful response with a consistent envelope."""
    return jsonify({"success": True, "data": data}), int(status)


def error_response(
    code: str,
    message: str,
    *,
    status: HTTPStatus | int = HTTPStatus.BAD_REQUEST,
    details: Any = None,
) -> tuple[Response, int]:
    """Return an error response with a consistent envelope."""
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return jsonify({"success": False, "error": error}), int(status)
