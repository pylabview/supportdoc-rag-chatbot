from __future__ import annotations

import logging
from time import perf_counter

from fastapi import FastAPI, Request, Response

from supportdoc_rag_chatbot.logging_conf import (
    REQUEST_ID_HEADER,
    log_event,
    normalize_request_id,
    request_id_context,
)

logger = logging.getLogger(__name__)


def register_api_middleware(app: FastAPI) -> None:
    """Register request correlation and lifecycle logging middleware."""

    @app.middleware("http")
    async def _request_logging_middleware(request: Request, call_next):
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        request.state.request_started_at = perf_counter()
        path = request.url.path
        method = request.method
        response: Response | None = None
        status_code = 500

        with request_id_context(request_id):
            log_event(
                logger,
                "api.request.started",
                method=method,
                path=path,
                route=_resolve_route_path(request),
            )
            try:
                response = await call_next(request)
                status_code = response.status_code
                response.headers[REQUEST_ID_HEADER] = request_id
                return response
            finally:
                duration_ms = round((perf_counter() - request.state.request_started_at) * 1000, 3)
                log_event(
                    logger,
                    "api.request.completed",
                    method=method,
                    path=path,
                    route=_resolve_route_path(request),
                    status_code=status_code,
                    duration_ms=duration_ms,
                )


def _resolve_route_path(request: Request) -> str:
    route = request.scope.get("route")
    for attribute in ("path", "path_format"):
        value = getattr(route, attribute, None)
        if isinstance(value, str) and value.strip():
            return value
    return request.url.path


__all__ = ["register_api_middleware"]
