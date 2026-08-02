"""Common application exceptions and Flask error handlers."""

from http import HTTPStatus
from typing import Any

from flask import Flask
from werkzeug.exceptions import HTTPException

from app.responses import error_response


class APIError(Exception):
    """Expected API exception represented by the common error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status: HTTPStatus | int = HTTPStatus.BAD_REQUEST,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def register_error_handlers(app: Flask) -> None:
    """Register handlers for application, HTTP, and unexpected exceptions."""

    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        return error_response(
            error.code,
            error.message,
            status=error.status,
            details=error.details,
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return error_response(
            error.name.upper().replace(" ", "_"),
            error.description,
            status=error.code or HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled exception", exc_info=error)
        return error_response(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
