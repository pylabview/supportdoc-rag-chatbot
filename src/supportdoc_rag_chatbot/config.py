from __future__ import annotations

import os
import re
from enum import StrEnum
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Literal, Mapping
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from supportdoc_rag_chatbot.app.client import (
    DEFAULT_GENERATION_TIMEOUT_SECONDS,
    GenerationBackendMode,
)
from supportdoc_rag_chatbot.app.core.retrieval import RetrievalBackendMode
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_PGVECTOR_RUNTIME_ID,
    DEFAULT_PGVECTOR_SCHEMA_NAME,
    validate_pgvector_schema_name,
)

DEFAULT_API_TITLE = "SupportDoc RAG Chatbot API"
DEFAULT_API_ENVIRONMENT = "local"
DEFAULT_API_DOCS_URL = "/docs"
DEFAULT_API_REDOC_URL = "/redoc"
DEFAULT_QUERY_RETRIEVAL_MODE = RetrievalBackendMode.FIXTURE
DEFAULT_QUERY_GENERATION_MODE = GenerationBackendMode.FIXTURE
DEFAULT_QUERY_TOP_K = 3
DEFAULT_QUERY_ARTIFACT_EMBEDDER_MODE: Literal["local", "fixture"] = "local"
DEFAULT_QUERY_PGVECTOR_EMBEDDER_MODE: Literal["local", "fixture"] = "local"
DEFAULT_API_CORS_ALLOWED_ORIGINS: tuple[str, ...] = ()
DEFAULT_API_CORS_ALLOWED_ORIGIN_REGEX: str | None = None


class DeploymentTarget(StrEnum):
    """Supported runtime deployment targets for the backend API."""

    LOCAL = "local"
    AWS = "aws"


DEFAULT_DEPLOYMENT_TARGET = DeploymentTarget.LOCAL


class BackendSettings(BaseModel):
    """Boot-time settings shared by the backend API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    app_name: str = Field(default=DEFAULT_API_TITLE)
    environment: str = Field(default=DEFAULT_API_ENVIRONMENT)
    api_version: str = Field(default_factory=lambda: _default_api_version())
    docs_url: str = Field(default=DEFAULT_API_DOCS_URL)
    redoc_url: str = Field(default=DEFAULT_API_REDOC_URL)
    deployment_target: DeploymentTarget = Field(default=DEFAULT_DEPLOYMENT_TARGET)
    api_cors_allowed_origins: tuple[str, ...] = Field(default=DEFAULT_API_CORS_ALLOWED_ORIGINS)
    api_cors_allowed_origin_regex: str | None = Field(default=DEFAULT_API_CORS_ALLOWED_ORIGIN_REGEX)
    query_retrieval_mode: RetrievalBackendMode = Field(default=DEFAULT_QUERY_RETRIEVAL_MODE)
    query_generation_mode: GenerationBackendMode = Field(default=DEFAULT_QUERY_GENERATION_MODE)
    query_generation_base_url: str | None = None
    query_generation_model: str | None = None
    query_generation_api_key: str | None = Field(default=None, repr=False)
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
    query_pgvector_dsn: str | None = Field(default=None, repr=False)
    query_pgvector_schema_name: str = Field(default=DEFAULT_PGVECTOR_SCHEMA_NAME)
    query_pgvector_runtime_id: str = Field(default=DEFAULT_PGVECTOR_RUNTIME_ID)
    query_pgvector_embedder_mode: Literal["local", "fixture"] = Field(
        default=DEFAULT_QUERY_PGVECTOR_EMBEDDER_MODE
    )
    query_pgvector_embedder_fixture_path: str | None = None

    @field_validator(
        "app_name",
        "environment",
        "api_version",
        "docs_url",
        "redoc_url",
        "query_pgvector_runtime_id",
        "query_pgvector_schema_name",
    )
    @classmethod
    def _validate_non_blank(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized

    @field_validator(
        "query_generation_base_url",
        "query_generation_model",
        "query_generation_api_key",
        "query_artifact_chunks_path",
        "query_artifact_index_path",
        "query_artifact_index_metadata_path",
        "query_artifact_row_mapping_path",
        "query_artifact_embedder_fixture_path",
        "query_pgvector_dsn",
        "query_pgvector_embedder_fixture_path",
    )
    @classmethod
    def _validate_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("api_cors_allowed_origins", mode="before")
    @classmethod
    def _validate_api_cors_allowed_origins(
        cls, value: tuple[str, ...] | list[str] | str | None
    ) -> tuple[str, ...]:
        if value is None:
            return ()

        if isinstance(value, str):
            raw_values = [value]
        else:
            raw_values = list(value)

        normalized_origins: list[str] = []
        seen: set[str] = set()
        for raw_value in raw_values:
            origin = _normalize_browser_origin(str(raw_value))
            if origin not in seen:
                normalized_origins.append(origin)
                seen.add(origin)
        return tuple(normalized_origins)

    @field_validator("api_cors_allowed_origin_regex")
    @classmethod
    def _validate_api_cors_allowed_origin_regex(cls, value: str | None) -> str | None:
        normalized = cls._validate_optional_string(value)
        if normalized is None:
            return None
        try:
            re.compile(normalized)
        except re.error as exc:
            raise ValueError(
                "api_cors_allowed_origin_regex must be a valid regular expression"
            ) from exc
        return normalized

    @field_validator("query_artifact_embedder_mode", "query_pgvector_embedder_mode")
    @classmethod
    def _validate_embedder_mode(cls, value: str, info) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"local", "fixture"}:
            raise ValueError(f"{info.field_name} must be 'local' or 'fixture'")
        return normalized

    @field_validator("query_pgvector_schema_name")
    @classmethod
    def _validate_pgvector_schema_name(cls, value: str) -> str:
        return validate_pgvector_schema_name(value)

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

    @model_validator(mode="after")
    def _validate_runtime_dependencies(self) -> "BackendSettings":
        if self.query_retrieval_mode is RetrievalBackendMode.PGVECTOR:
            if not self.query_pgvector_dsn:
                raise ValueError(
                    "SUPPORTDOC_QUERY_PGVECTOR_DSN is required when "
                    "SUPPORTDOC_QUERY_RETRIEVAL_MODE=pgvector."
                )
            if (
                self.query_pgvector_embedder_mode == "fixture"
                and not self.query_pgvector_embedder_fixture_path
            ):
                raise ValueError(
                    "SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_FIXTURE_PATH is required when "
                    "SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_MODE=fixture."
                )

        if self.query_generation_mode is GenerationBackendMode.OPENAI_COMPATIBLE:
            if not self.query_generation_base_url:
                raise ValueError(
                    "SUPPORTDOC_QUERY_GENERATION_BASE_URL is required when "
                    "SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible."
                )
            if not self.query_generation_model:
                raise ValueError(
                    "SUPPORTDOC_QUERY_GENERATION_MODEL is required when "
                    "SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible."
                )

        return self

    @model_validator(mode="after")
    def _validate_deployment_target_runtime(self) -> "BackendSettings":
        if self.deployment_target is not DeploymentTarget.AWS:
            return self

        if self.query_retrieval_mode is RetrievalBackendMode.ARTIFACT:
            raise ValueError(
                "SUPPORTDOC_DEPLOYMENT_TARGET=aws does not support "
                "SUPPORTDOC_QUERY_RETRIEVAL_MODE=artifact in the current repo. "
                "Artifact retrieval is the local FAISS path only. Use "
                "SUPPORTDOC_QUERY_RETRIEVAL_MODE=fixture or "
                "SUPPORTDOC_QUERY_RETRIEVAL_MODE=pgvector for the AWS backend path."
            )

        if not self.api_cors_allowed_origins and not self.api_cors_allowed_origin_regex:
            raise ValueError(
                "SUPPORTDOC_DEPLOYMENT_TARGET=aws requires either "
                "SUPPORTDOC_API_CORS_ALLOWED_ORIGINS or "
                "SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX so the backend does not fall back "
                "to localhost-only browser access."
            )

        if (
            self.query_generation_mode is GenerationBackendMode.HTTP
            and not self.query_generation_base_url
        ):
            raise ValueError(
                "SUPPORTDOC_DEPLOYMENT_TARGET=aws with SUPPORTDOC_QUERY_GENERATION_MODE=http "
                "requires SUPPORTDOC_QUERY_GENERATION_BASE_URL."
            )

        return self


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
        deployment_target=DeploymentTarget(
            _read_env_string(
                source,
                "SUPPORTDOC_DEPLOYMENT_TARGET",
                default=DEFAULT_DEPLOYMENT_TARGET.value,
            )
        ),
        api_cors_allowed_origins=_read_env_csv_strings(
            source,
            "SUPPORTDOC_API_CORS_ALLOWED_ORIGINS",
        ),
        api_cors_allowed_origin_regex=_read_env_optional_string(
            source,
            "SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX",
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
        query_generation_model=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_GENERATION_MODEL",
        ),
        query_generation_api_key=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_GENERATION_API_KEY",
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
        query_pgvector_dsn=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_PGVECTOR_DSN",
        ),
        query_pgvector_schema_name=_read_env_string(
            source,
            "SUPPORTDOC_QUERY_PGVECTOR_SCHEMA_NAME",
            default=DEFAULT_PGVECTOR_SCHEMA_NAME,
        ),
        query_pgvector_runtime_id=_read_env_string(
            source,
            "SUPPORTDOC_QUERY_PGVECTOR_RUNTIME_ID",
            default=DEFAULT_PGVECTOR_RUNTIME_ID,
        ),
        query_pgvector_embedder_mode=_read_env_string(
            source,
            "SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_MODE",
            default=DEFAULT_QUERY_PGVECTOR_EMBEDDER_MODE,
        ),
        query_pgvector_embedder_fixture_path=_read_env_optional_string(
            source,
            "SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_FIXTURE_PATH",
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


def _read_env_csv_strings(source: Mapping[str, str], key: str) -> tuple[str, ...]:
    value = source.get(key)
    if value is None:
        return ()

    parts = [part.strip() for part in value.split(",")]
    return tuple(part for part in parts if part)


def _normalize_browser_origin(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        raise ValueError("browser origin entries must not be blank")

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "browser origin entries must include an http:// or https:// origin without a path"
        )

    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("browser origin entries must not include a path, query, or fragment")

    return f"{parsed.scheme}://{parsed.netloc}"


__all__ = [
    "BackendSettings",
    "DEFAULT_API_DOCS_URL",
    "DEFAULT_API_ENVIRONMENT",
    "DEFAULT_API_REDOC_URL",
    "DEFAULT_API_TITLE",
    "DEFAULT_API_CORS_ALLOWED_ORIGIN_REGEX",
    "DEFAULT_API_CORS_ALLOWED_ORIGINS",
    "DEFAULT_DEPLOYMENT_TARGET",
    "DEFAULT_QUERY_ARTIFACT_EMBEDDER_MODE",
    "DEFAULT_QUERY_GENERATION_MODE",
    "DEFAULT_QUERY_PGVECTOR_EMBEDDER_MODE",
    "DEFAULT_QUERY_RETRIEVAL_MODE",
    "DEFAULT_QUERY_TOP_K",
    "DeploymentTarget",
    "clear_backend_settings_cache",
    "get_backend_settings",
    "get_request_settings",
    "load_backend_settings",
]
