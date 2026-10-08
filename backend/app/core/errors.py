"""One error format for the whole API: {code, message, details, request_id} (docs/04 section 9).

`message` is a translation key (for example "errors.not_found"); the frontend renders it.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class AppError(Exception):
    """Raise this from services and routers. Subclass for common cases."""

    status_code = 400
    code = "bad_request"

    def __init__(
        self, code: str | None = None, details: Any = None, status_code: int | None = None
    ):
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.code)


class NotFoundError(AppError):
    status_code, code = 404, "not_found"


class ForbiddenError(AppError):
    status_code, code = 403, "forbidden"


class ConflictError(AppError):
    status_code, code = 409, "conflict"


def _response(status_code: int, code: str, details: Any = None) -> JSONResponse:
    body = ErrorBody(
        code=code, message=f"errors.{code}", details=details, request_id=request_id_var.get()
    )
    return JSONResponse(body.model_dump(), status_code=status_code)


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # narrows the type for mypy
        raise exc
    return _response(exc.status_code, exc.code, exc.details)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # narrows the type for mypy
        raise exc
    code = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
    return _response(exc.status_code, code)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # narrows the type for mypy
        raise exc
    # Only location, type and message: never echo the submitted input (may hold secrets).
    details = [{"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in exc.errors()]
    return _response(422, "validation_error", details)


def internal_error_response() -> JSONResponse:
    """Used by RequestContextMiddleware, which catches unhandled errors while the request ID
    is still known (Starlette's own 500 handler runs outside all middleware)."""
    return _response(500, "internal_error")


# PostgreSQL error codes for constraint violations the client caused (bad input, not a bug).
_CONSTRAINT_ERRORS = {
    "23503": (422, "invalid_reference"),  # foreign key: e.g. a role or outlet of another tenant
    "23505": (409, "conflict"),  # unique violation
    "23514": (422, "validation_error"),  # check constraint
}


async def _integrity_error(_: Request, exc: Exception) -> JSONResponse:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    status, error = _CONSTRAINT_ERRORS.get(str(code), (409, "conflict"))
    # The constraint name goes to the server log only (no values: they may be personal data).
    cause = getattr(orig, "__cause__", None)
    log.warning("integrity error %s on %s", code, getattr(cause, "constraint_name", None))
    # No constraint names or SQL in the response: they reveal the schema.
    return _response(status, error)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
