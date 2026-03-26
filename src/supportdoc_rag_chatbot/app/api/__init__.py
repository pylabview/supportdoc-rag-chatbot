from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from supportdoc_rag_chatbot.app.core import close_cached_query_orchestrator
from supportdoc_rag_chatbot.config import BackendSettings, get_backend_settings
from supportdoc_rag_chatbot.logging_conf import configure_logging

from .errors import register_exception_handlers
from .middleware import register_api_middleware
from .routes import query_router, system_router


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    try:
        yield
    finally:
        close_cached_query_orchestrator(app)


def create_app(*, settings: BackendSettings | None = None) -> FastAPI:
    """Create the bootable FastAPI application shell for backend work."""

    configure_logging()
    resolved_settings = settings or get_backend_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.api_version,
        docs_url=resolved_settings.docs_url,
        redoc_url=resolved_settings.redoc_url,
        lifespan=_app_lifespan,
    )
    app.state.settings = resolved_settings

    register_api_middleware(app)
    register_exception_handlers(app)
    app.include_router(system_router)
    app.include_router(query_router)
    return app


app = create_app()

__all__ = ["app", "create_app"]
