from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any, Protocol, runtime_checkable

from supportdoc_rag_chatbot.app.schemas import QueryResponse


class GenerationBackendMode(StrEnum):
    """Supported generation backend modes for backend orchestration."""

    FIXTURE = "fixture"
    HTTP = "http"


class GenerationFailureCode(StrEnum):
    """Normalized failure categories emitted by generation backends."""

    PARSE_ERROR = "parse_error"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    BACKEND_ERROR = "backend_error"


@dataclass(slots=True, frozen=True)
class GenerationRequest:
    """Backend-agnostic generation request passed into a generation client."""

    question: str
    system_prompt: str | None = None
    user_prompt: str | None = None
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "question", _validate_required_string(self.question, field_name="question")
        )
        object.__setattr__(self, "system_prompt", _normalize_optional_string(self.system_prompt))
        object.__setattr__(self, "user_prompt", _normalize_optional_string(self.user_prompt))
        object.__setattr__(
            self, "timeout_seconds", _validate_optional_timeout(self.timeout_seconds)
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        """Return a deterministic JSON-serializable request payload."""

        payload: dict[str, Any] = {"question": self.question}
        if self.system_prompt is not None:
            payload["system_prompt"] = self.system_prompt
        if self.user_prompt is not None:
            payload["user_prompt"] = self.user_prompt
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(slots=True, frozen=True)
class GenerationFailure:
    """Normalized backend failure returned to the orchestration layer."""

    code: GenerationFailureCode
    message: str
    backend_name: str
    retryable: bool = False
    status_code: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "message", _validate_required_string(self.message, field_name="message")
        )
        object.__setattr__(
            self,
            "backend_name",
            _validate_required_string(self.backend_name, field_name="backend_name"),
        )
        object.__setattr__(self, "details", dict(self.details))
        if self.status_code is not None and self.status_code <= 0:
            raise ValueError("status_code must be > 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "backend_name": self.backend_name,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "details": dict(self.details),
        }


@dataclass(slots=True, frozen=True)
class GenerationResult:
    """Result envelope for generation clients."""

    response: QueryResponse | None = None
    failure: GenerationFailure | None = None

    def __post_init__(self) -> None:
        if (self.response is None) == (self.failure is None):
            raise ValueError("GenerationResult must contain exactly one of response or failure")

    @property
    def is_success(self) -> bool:
        return self.response is not None

    @property
    def is_failure(self) -> bool:
        return self.failure is not None

    def require_response(self) -> QueryResponse:
        if self.response is None:
            raise ValueError("GenerationResult does not contain a response")
        return self.response

    @classmethod
    def success(cls, response: QueryResponse) -> "GenerationResult":
        return cls(response=response)

    @classmethod
    def from_failure(cls, failure: GenerationFailure) -> "GenerationResult":
        return cls(failure=failure)


@runtime_checkable
class GenerationClient(Protocol):
    """Backend-agnostic generation client interface."""

    backend_mode: GenerationBackendMode
    backend_name: str

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate a response or return a normalized backend failure."""

    def close(self) -> None:
        """Release any backend resources held by the client."""


def _validate_required_string(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _validate_optional_timeout(value: float | None) -> float | None:
    if value is None:
        return None
    if not isfinite(value) or value <= 0:
        raise ValueError("timeout_seconds must be a finite value > 0")
    return float(value)


__all__ = [
    "GenerationBackendMode",
    "GenerationClient",
    "GenerationFailure",
    "GenerationFailureCode",
    "GenerationRequest",
    "GenerationResult",
]
