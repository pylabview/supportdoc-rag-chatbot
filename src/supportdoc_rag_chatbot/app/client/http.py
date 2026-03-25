from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import httpx
from pydantic import ValidationError

from supportdoc_rag_chatbot.app.schemas import QueryResponse

from .types import (
    GenerationBackendMode,
    GenerationFailure,
    GenerationFailureCode,
    GenerationRequest,
    GenerationResult,
)

DEFAULT_GENERATION_HTTP_ENDPOINT_PATH = "/query"
DEFAULT_GENERATION_TIMEOUT_SECONDS = 30.0


@dataclass(slots=True)
class HttpGenerationClient:
    """Thin HTTP generation client for future remote model endpoints."""

    base_url: str
    endpoint_path: str = DEFAULT_GENERATION_HTTP_ENDPOINT_PATH
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS
    headers: Mapping[str, str] = field(default_factory=dict)
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = _normalize_base_url(self.base_url)
        self.endpoint_path = _normalize_endpoint_path(self.endpoint_path)
        self.timeout_seconds = _validate_timeout_seconds(self.timeout_seconds)
        self.headers = dict(self.headers)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self.headers,
            transport=self.transport,
        )

    @property
    def backend_mode(self) -> GenerationBackendMode:
        return GenerationBackendMode.HTTP

    @property
    def backend_name(self) -> str:
        return self.backend_mode.value

    def generate(self, request: GenerationRequest) -> GenerationResult:
        timeout_seconds = request.timeout_seconds or self.timeout_seconds
        try:
            response = self._client.post(
                self.endpoint_path,
                json=request.to_payload(),
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            return GenerationResult.from_failure(
                GenerationFailure(
                    code=GenerationFailureCode.TIMEOUT,
                    message="Generation backend request timed out.",
                    backend_name=self.backend_name,
                    retryable=True,
                    details={"error": str(exc), "timeout_seconds": timeout_seconds},
                )
            )
        except httpx.TransportError as exc:
            return GenerationResult.from_failure(
                GenerationFailure(
                    code=GenerationFailureCode.TRANSPORT_ERROR,
                    message="Generation backend transport error.",
                    backend_name=self.backend_name,
                    retryable=True,
                    details={"error": str(exc)},
                )
            )

        if response.is_error:
            return GenerationResult.from_failure(
                GenerationFailure(
                    code=GenerationFailureCode.BACKEND_ERROR,
                    message=f"Generation backend returned HTTP {response.status_code}.",
                    backend_name=self.backend_name,
                    retryable=response.status_code >= 500 or response.status_code == 429,
                    status_code=response.status_code,
                    details={"response_text": response.text},
                )
            )

        try:
            payload = response.json()
            parsed = QueryResponse.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            return GenerationResult.from_failure(
                GenerationFailure(
                    code=GenerationFailureCode.PARSE_ERROR,
                    message="Generation backend returned an invalid QueryResponse payload.",
                    backend_name=self.backend_name,
                    retryable=False,
                    status_code=response.status_code,
                    details={"error": str(exc), "response_text": response.text},
                )
            )

        return GenerationResult.success(parsed)

    def close(self) -> None:
        self._client.close()


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("base_url must not be blank")
    return normalized


def _normalize_endpoint_path(endpoint_path: str) -> str:
    normalized = endpoint_path.strip()
    if not normalized:
        raise ValueError("endpoint_path must not be blank")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _validate_timeout_seconds(value: float) -> float:
    request = GenerationRequest(question="timeout validation sentinel", timeout_seconds=value)
    assert request.timeout_seconds is not None
    return request.timeout_seconds


__all__ = [
    "DEFAULT_GENERATION_HTTP_ENDPOINT_PATH",
    "DEFAULT_GENERATION_TIMEOUT_SECONDS",
    "HttpGenerationClient",
]
