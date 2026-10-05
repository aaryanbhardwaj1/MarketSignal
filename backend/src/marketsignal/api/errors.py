"""Uniform error envelope: ``{"error": {"code": ..., "message": ..., ...}}``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from marketsignal.domain.enums import IngestErrorCode
from marketsignal.ingestion.models import IngestionError

UPLOAD_ERROR_STATUS = {
    IngestErrorCode.UNSUPPORTED_TYPE.value: 415,
    IngestErrorCode.FILE_TOO_LARGE.value: 413,
    IngestErrorCode.CONTENT_TOO_LARGE.value: 413,
    IngestErrorCode.SOURCE_TYPE_MISMATCH.value: 409,
}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def error_body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, **exc.extra), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"location": ".".join(str(p) for p in e.get("loc", ())), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(
            error_body("VALIDATION_ERROR", "request validation failed", fields=fields),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            error_body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(IngestionError)
    async def _ingestion_error(_: Request, exc: IngestionError) -> JSONResponse:
        status = UPLOAD_ERROR_STATUS.get(exc.code, 422)
        return JSONResponse(error_body(exc.code, exc.message), status_code=status)
