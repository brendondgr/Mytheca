"""Error envelope.

Every error response uses the contract shape (``docs/api-contract.md``):

    { "error": { "code": "string", "message": "string", "details": {} } }

Services raise ``APIError``; the registered handlers also reshape FastAPI's
routing 404s and 422 validation errors into the same envelope.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


class APIError(Exception):
    """Raised by services; carries the HTTP status and the envelope fields."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def _envelope(code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


async def _api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, exc.details),
    )


async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "error")
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, str(exc.detail), {}),
    )


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_envelope(
            "validation_error",
            "Request validation failed.",
            {"errors": jsonable_encoder(exc.errors())},
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
