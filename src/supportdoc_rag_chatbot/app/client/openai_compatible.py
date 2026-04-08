from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx
from pydantic import ValidationError

from supportdoc_rag_chatbot.app.schemas import QueryResponse

from .http import DEFAULT_GENERATION_TIMEOUT_SECONDS
from .types import (
    GenerationBackendMode,
    GenerationFailure,
    GenerationFailureCode,
    GenerationRequest,
    GenerationResult,
)

DEFAULT_OPENAI_COMPATIBLE_ENDPOINT_PATH = "/v1/chat/completions"
DEFAULT_OPENAI_COMPATIBLE_TEMPERATURE = 0.0


@dataclass(slots=True)
class OpenAICompatibleGenerationClient:
    """Generation client for OpenAI-compatible chat completion endpoints."""

    base_url: str
    model: str
    api_key: str | None = None
    endpoint_path: str = DEFAULT_OPENAI_COMPATIBLE_ENDPOINT_PATH
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS
    headers: Mapping[str, str] = field(default_factory=dict)
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = _normalize_base_url(self.base_url)
        self.model = _validate_required_string(self.model, field_name="model")
        self.api_key = _normalize_optional_string(self.api_key)
        self.endpoint_path = _normalize_endpoint_path(self.endpoint_path)
        self.timeout_seconds = _validate_timeout_seconds(self.timeout_seconds)
        normalized_headers = {str(key): str(value) for key, value in self.headers.items()}
        if self.api_key is not None:
            normalized_headers.setdefault("Authorization", f"Bearer {self.api_key}")
        self.headers = normalized_headers
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self.headers,
            transport=self.transport,
        )

    @property
    def backend_mode(self) -> GenerationBackendMode:
        return GenerationBackendMode.OPENAI_COMPATIBLE

    @property
    def backend_name(self) -> str:
        return self.backend_mode.value

    def generate(self, request: GenerationRequest) -> GenerationResult:
        timeout_seconds = request.timeout_seconds or self.timeout_seconds
        payload = {
            "model": self.model,
            "messages": _build_messages(request),
            "temperature": DEFAULT_OPENAI_COMPATIBLE_TEMPERATURE,
        }
        try:
            response = self._client.post(
                self.endpoint_path,
                json=payload,
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
            response_payload = response.json()
            content = extract_openai_compatible_content(response_payload)
            parsed = parse_query_response_content(content)
        except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError) as exc:
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


def extract_openai_compatible_content(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, Sequence) or not choices:
        raise ValueError("OpenAI-compatible response is missing choices[0].message.content")
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise ValueError("OpenAI-compatible response choices[0] must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("OpenAI-compatible response choices[0].message must be an object")
    content = message.get("content")
    if isinstance(content, str):
        normalized = content.strip()
        if not normalized:
            raise ValueError("OpenAI-compatible response content must not be blank")
        return normalized
    if isinstance(content, Sequence):
        text_parts: list[str] = []
        for part in content:
            if not isinstance(part, Mapping):
                continue
            if str(part.get("type", "")).casefold() != "text":
                continue
            text_value = part.get("text")
            if text_value is None:
                continue
            normalized_text = str(text_value).strip()
            if normalized_text:
                text_parts.append(normalized_text)
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("OpenAI-compatible response content must be a text string")


def parse_query_response_content(content: str) -> QueryResponse:
    normalized = _validate_required_string(content, field_name="content")
    candidates = [normalized]
    stripped_fence = _strip_markdown_json_fence(normalized)
    if stripped_fence is not None and stripped_fence != normalized:
        candidates.append(stripped_fence)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            return QueryResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _build_messages(request: GenerationRequest) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if request.system_prompt is not None:
        messages.append({"role": "system", "content": request.system_prompt})
    user_content = request.user_prompt or request.question
    messages.append({"role": "user", "content": user_content})
    return messages


def _strip_markdown_json_fence(content: str) -> str | None:
    normalized = content.strip()
    if not normalized.startswith("```") or not normalized.endswith("```"):
        return None
    lines = normalized.splitlines()
    if len(lines) < 3:
        return None
    if not lines[0].startswith("```"):
        return None
    if lines[-1] != "```":
        return None
    return "\n".join(lines[1:-1]).strip()


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


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_required_string(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _validate_timeout_seconds(value: float) -> float:
    request = GenerationRequest(question="timeout validation sentinel", timeout_seconds=value)
    assert request.timeout_seconds is not None
    return request.timeout_seconds


__all__ = [
    "DEFAULT_OPENAI_COMPATIBLE_ENDPOINT_PATH",
    "DEFAULT_OPENAI_COMPATIBLE_TEMPERATURE",
    "OpenAICompatibleGenerationClient",
    "extract_openai_compatible_content",
    "parse_query_response_content",
]
