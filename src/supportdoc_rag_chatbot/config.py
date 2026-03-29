from __future__ import annotations

import os
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Literal, Mapping

from dotenv import load_dotenv
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from supportdoc_rag_chatbot.app.client import (
    DEFAULT_GENERATION_TIMEOUT_SECONDS,
    GenerationBackendMode,
)
from supportdoc_rag_chatbot.app.core.retrieval import RetrievalBackendMode

DEFAULT_API_TITLE = "SupportDoc RAG Chatbot API"
DEFAULT_API_ENVIRONMENT = "local"
DEFAULT_API_DOCS_URL = "/docs"
DEFAULT_API_REDOC_URL = "/redoc"
DEFAULT_QUERY_RETRIEVAL_MODE = RetrievalBackendMode.FIXTURE
DEFAULT_QUERY_GENERATION_MODE = GenerationBackendMode.FIXTURE
DEFAULT_QUERY_TOP_K = 3
DEFAULT_QUERY_ARTIFACT_EMBEDDER_MODE: Literal["local", "fixture"] = "local"


class BackendSettings(BaseModel):
    """Boot-time settings shared by the backend API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    app_name: str = Field(default=DEFAULT_API_TITLE)
    environment: str = Field(default=DEFAULT_API_ENVIRONMENT)
    api_version: str = Field(default_factory=lambda: _default_api_version())
    docs_url: str = Field(default=DEFAULT_API_DOCS_URL)
    redoc_url: str = Field(default=DEFAULT_API_REDOC_URL)
    query_retrieval_mode: RetrievalBackendMode = Field(default=DEFAULT_QUERY_RETRIEVAL_MODE)
    query_generation_mode: GenerationBackendMode = Field(default=DEFAULT_QUERY_GENERATION_MODE)
    query_generation_base_url: str | None = None
    query_generation_timeout_seconds: float = Field(default=DEFAULT_GENERATION_TIMEOUT_SECONDS)
    query_top_k: int = Field(default=DEFAULT_QUERY_TOP_K)
    query_artifact_chunks_path: str | None = None
    query_artifact_index_path: str | None = None
    query_artifact_index_metadata_path: str | None = None
    query_artifact_row_mapping_path: str | None = None
    query_artifact_embedder_mode: Literal["local", "fixture"] = Field(
        default=DEFAULT_QUERY_ARTIFACT_EMBEDDER_MODE
    )
    query_artifact_embedder_fixture_path: str | None = None

    @field_validator(
        "app_name",
        "environment",
        "api_version",
        "docs_url",
        "redoc_url",
    )
    @classmethod
    def _validate_non_blank(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized

    @field_validator(
        "query_generation_base_url",
        "query_artifact_chunks_path",
        "query_artifact_index_path",
        "query_artifact_index_metadata_path",
        "query_artifact_row_mapping_path",
        "query_artifact_embedder_fixture_path",
    )
    @classmethod
    def _validate_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("query_artifact_embedder_mode")
    @classmethod
    def _validate_artifact_embedder_mode(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"local", "fixture"}:
            raise ValueError("query_artifact_embedder_mode must be 'local' or 'fixture'")
        return normalized

    @field_validator("query_generation_timeout_seconds")
    @classmethod
    def _validate_generation_timeout(cls, value: float) -> float:
        normalized = float(value)
        if normalized <= 0:
            raise ValueError("query_generation_timeout_seconds must be > 0")
        return normalized

    @field_validator("query_top_k")
    @classmethod
    def _validate_query_top_k(cls, value: int) -> int:
        normalized = int(value)
        if normalized <= 0:
            raise ValueError("query_top_k must be > 0")
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
        query_retrieval_mode=RetrievalBackendMode(
            _read_env_string(
                source,
                "SUPPORTDOC_QUERY_RETRIEVAL_MODE",
                default=DEFAULT_QUERY_RETRIEVAL_MODE.value,
            )
        ),
        query_generation_mode=GenerationBackendMode(
            _read_env_string(
                source,
                "SUPPORTDOC_QUERY_GENERATION_MODE",
                default=DEFAULT_QUERY_GENERATION_MODE.value,
            )
        ),
        query_generation_base_url=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_GENERATION_BASE_URL",
        ),
        query_generation_timeout_seconds=_read_env_float(
            source,
            "SUPPORTDOC_QUERY_GENERATION_TIMEOUT_SECONDS",
            default=DEFAULT_GENERATION_TIMEOUT_SECONDS,
        ),
        query_top_k=_read_env_int(
            source,
            "SUPPORTDOC_QUERY_TOP_K",
            default=DEFAULT_QUERY_TOP_K,
        ),
        query_artifact_chunks_path=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH",
        ),
        query_artifact_index_path=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_ARTIFACT_INDEX_PATH",
        ),
        query_artifact_index_metadata_path=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_ARTIFACT_INDEX_METADATA_PATH",
        ),
        query_artifact_row_mapping_path=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_ARTIFACT_ROW_MAPPING_PATH",
        ),
        query_artifact_embedder_mode=_read_env_string(
            source,
            "SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_MODE",
            default=DEFAULT_QUERY_ARTIFACT_EMBEDDER_MODE,
        ),
        query_artifact_embedder_fixture_path=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_FIXTURE_PATH",
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


def _read_env_optional_string(source: Mapping[str, str], key: str) -> str | None:
    value = source.get(key)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _read_env_int(source: Mapping[str, str], key: str, *, default: int) -> int:
    value = source.get(key)
    if value is None or not value.strip():
        return default
    return int(value)


def _read_env_float(source: Mapping[str, str], key: str, *, default: float) -> float:
    value = source.get(key)
    if value is None or not value.strip():
        return default
    return float(value)


__all__ = [
    "BackendSettings",
    "DEFAULT_API_DOCS_URL",
    "DEFAULT_API_ENVIRONMENT",
    "DEFAULT_API_REDOC_URL",
    "DEFAULT_API_TITLE",
    "DEFAULT_QUERY_ARTIFACT_EMBEDDER_MODE",
    "DEFAULT_QUERY_GENERATION_MODE",
    "DEFAULT_QUERY_RETRIEVAL_MODE",
    "DEFAULT_QUERY_TOP_K",
    "clear_backend_settings_cache",
    "get_backend_settings",
    "get_request_settings",
    "load_backend_settings",
]
