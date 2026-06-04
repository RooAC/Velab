"""Shared API error response helpers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def api_error(
    code: str,
    message: str,
    http_status: int,
    *,
    details: Any | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=http_status, content=body)


def _code_for_status(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "HTTP_ERROR")


def _normalize_http_detail(detail: Any, status_code: int) -> tuple[str, str, Any | None]:
    if isinstance(detail, dict):
        nested = detail.get("error")
        if isinstance(nested, dict):
            code = str(nested.get("code") or _code_for_status(status_code))
            message = str(nested.get("message") or "Request failed")
            return code, message, nested.get("details")
        code = str(detail.get("code") or _code_for_status(status_code))
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
        return code, message, detail.get("details")
    return _code_for_status(status_code), str(detail or "Request failed"), None


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code, message, details = _normalize_http_detail(exc.detail, exc.status_code)
        return api_error(code, message, exc.status_code, details=details)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return api_error(
            "VALIDATION_ERROR",
            "Request validation failed",
            422,
            details=jsonable_encoder(exc.errors()),
        )
