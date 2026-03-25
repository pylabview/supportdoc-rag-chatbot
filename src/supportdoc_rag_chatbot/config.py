from __future__ import annotations

import os
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Mapping

from dotenv import load_dotenv
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_API_TITLE = "SupportDoc RAG Chatbot API"
DEFAULT_API_ENVIRONMENT = "local"
DEFAULT_API_DOCS_URL = "/docs"
DEFAULT_API_REDOC_URL = "/redoc"


class BackendSettings(BaseModel):
    """Boot-time settings shared by the backend API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    app_name: str = Field(default=DEFAULT_API_TITLE)
    environment: str = Field(default=DEFAULT_API_ENVIRONMENT)
    api_version: str = Field(default_factory=lambda: _default_api_version())
    docs_url: str = Field(default=DEFAULT_API_DOCS_URL)
    redoc_url: str = Field(default=DEFAULT_API_REDOC_URL)

    @field_validator("app_name", "environment", "api_version", "docs_url", "redoc_url")
    @classmethod
    def _validate_non_blank(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized


@lru_cache(maxsize=1)
def get_backend_settings() -> BackendSettings:
    """Return cached backend settings loaded from the process environment."""

    return load_backend_settings()


def load_backend_settings(environ: Mapping[str, str] | None = None) -> BackendSettings:
    """Load backend settings from a mapping or the current process environment."""

    load_dotenv()
    source = os.environ if environ is None else environ
    return BackendSettings(
        app_name=_read_env_string(source, "SUPPORTDOC_API_TITLE", default=DEFAULT_API_TITLE),
        environment=_read_env_string(source, "SUPPORTDOC_ENV", default=DEFAULT_API_ENVIRONMENT),
        api_version=_read_env_string(
            source,
            "SUPPORTDOC_API_VERSION",
            default=_default_api_version(),
        ),
        docs_url=_read_env_string(source, "SUPPORTDOC_API_DOCS_URL", default=DEFAULT_API_DOCS_URL),
        redoc_url=_read_env_string(
            source,
            "SUPPORTDOC_API_REDOC_URL",
            default=DEFAULT_API_REDOC_URL,
        ),
    )


def clear_backend_settings_cache() -> None:
    """Clear the cached backend settings instance."""

    get_backend_settings.cache_clear()


def get_request_settings(request: Request) -> BackendSettings:
    """Resolve request-scoped settings from app state, falling back to cached defaults."""

    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, BackendSettings):
        return settings
    return get_backend_settings()


def _default_api_version() -> str:
    try:
        return version("supportdoc-rag-chatbot")
    except PackageNotFoundError:
        return "0.1.0"


def _read_env_string(source: Mapping[str, str], key: str, *, default: str) -> str:
    value = source.get(key)
    if value is None:
        return default
    normalized = value.strip()
    if not normalized:
        return default
    return normalized


__all__ = [
    "BackendSettings",
    "DEFAULT_API_DOCS_URL",
    "DEFAULT_API_ENVIRONMENT",
    "DEFAULT_API_REDOC_URL",
    "DEFAULT_API_TITLE",
    "clear_backend_settings_cache",
    "get_backend_settings",
    "get_request_settings",
    "load_backend_settings",
]
