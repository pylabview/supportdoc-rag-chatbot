from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    """Minimal request contract for the first /query API shell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(description="End-user question text.")

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class HealthStatusResponse(BaseModel):
    """Minimal liveness payload returned by /healthz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]


class ReadinessStatusResponse(BaseModel):
    """Deterministic readiness payload returned by /readyz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready"]
    service: str
    environment: str
    version: str
    query_contract: Literal["QueryResponse"] = "QueryResponse"


class ApiError(BaseModel):
    """Machine-readable API error payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    details: list[dict[str, Any]] | None = None

    @field_validator("code", "message")
    @classmethod
    def _validate_non_blank(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized


class ApiErrorResponse(BaseModel):
    """Envelope for API error responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ApiError


__all__ = [
    "ApiError",
    "ApiErrorResponse",
    "HealthStatusResponse",
    "QueryRequest",
    "ReadinessStatusResponse",
]
