from __future__ import annotations

from fastapi import FastAPI

from supportdoc_rag_chatbot.config import BackendSettings, get_backend_settings

from .errors import register_exception_handlers
from .routes import query_router, system_router


def create_app(*, settings: BackendSettings | None = None) -> FastAPI:
    """Create the bootable FastAPI application shell for backend work."""

    resolved_settings = settings or get_backend_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.api_version,
        docs_url=resolved_settings.docs_url,
        redoc_url=resolved_settings.redoc_url,
    )
    app.state.settings = resolved_settings

    register_exception_handlers(app)
    app.include_router(system_router)
    app.include_router(query_router)
    return app


app = create_app()

__all__ = ["app", "create_app"]
