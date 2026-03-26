from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from supportdoc_rag_chatbot.app.core import QueryPipelineError
from supportdoc_rag_chatbot.logging_conf import log_event

from .schemas import ApiError, ApiErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register deterministic JSON exception handlers for the API shell."""

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        payload = ApiErrorResponse(
            error=ApiError(
                code="request_validation_error",
                message="Request validation failed.",
                details=_serialize_validation_details(exc.errors()),
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        del request
        payload = ApiErrorResponse(
            error=ApiError(
                code=f"http_{exc.status_code}",
                message=_normalize_http_detail(exc.detail),
            )
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(QueryPipelineError)
    async def _handle_query_pipeline_error(
        request: Request,
        exc: QueryPipelineError,
    ) -> JSONResponse:
        log_event(
            logger,
            "api.query_pipeline.error",
            level=logging.ERROR,
            exc_info=exc,
            path=str(request.url.path),
            error_code=exc.code,
        )
        payload = ApiErrorResponse(
            error=ApiError(
                code=exc.code,
                message=str(exc),
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        log_event(
            logger,
            "api.unhandled_exception",
            level=logging.ERROR,
            exc_info=exc,
            path=str(request.url.path),
            error_code="internal_server_error",
        )
        payload = ApiErrorResponse(
            error=ApiError(
                code="internal_server_error",
                message="Internal server error.",
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump())


def _normalize_http_detail(detail: Any) -> str:
    if isinstance(detail, str):
        normalized = detail.strip()
        if normalized:
            return normalized
    return "Request failed."


def _serialize_validation_details(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for detail in details:
        serialized = {
            "type": detail.get("type"),
            "loc": list(detail.get("loc", ())),
            "msg": detail.get("msg"),
        }
        if "input" in detail:
            serialized["input"] = detail["input"]
        payload.append(serialized)
    return payload


__all__ = ["register_exception_handlers"]
