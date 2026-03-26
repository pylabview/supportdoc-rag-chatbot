from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

PACKAGE_LOGGER_NAME = "supportdoc_rag_chatbot"
REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_LOG_FORMAT = "text"
DEFAULT_LOG_LEVEL = "INFO"
REDACTED_VALUE = "[redacted]"

_SUPPORTED_LOG_FORMATS = frozenset({"json", "text"})
_REQUEST_ID_VAR: ContextVar[str | None] = ContextVar("supportdoc_request_id", default=None)
_BASE_RECORD_FACTORY = logging.getLogRecordFactory()
_RECORD_FACTORY_INSTALLED = False
_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "content",
        "final_answer",
        "model_output",
        "output_text",
        "prompt",
        "question",
        "raw_output",
        "response_text",
        "retrieved_text",
        "system_prompt",
        "text",
        "user_prompt",
    }
)


class _SupportDocStreamHandler(logging.StreamHandler):
    """Marker handler used for idempotent package logger configuration."""


class JsonLogFormatter(logging.Formatter):
    """Render supportdoc log records as deterministic JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", None),
        }
        payload.update(_extract_extra_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, default=_json_default)


class TextLogFormatter(logging.Formatter):
    """Render supportdoc log records as compact key=value text."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        fields = {
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", None),
            **_extract_extra_fields(record),
        }
        rendered_fields = " ".join(
            f"{key}={_render_text_value(value)}"
            for key, value in fields.items()
            if value is not None
        )
        message = f"{timestamp} {rendered_fields}"
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return message


def configure_logging(
    *,
    log_format: str | None = None,
    log_level: str | int | None = None,
) -> logging.Logger:
    """Configure the package logger from one canonical module."""

    _install_record_factory()
    resolved_format = _resolve_log_format(log_format)
    resolved_level = _resolve_log_level(log_level)

    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    package_logger.setLevel(resolved_level)
    package_logger.propagate = False

    handlers = [
        handler
        for handler in package_logger.handlers
        if isinstance(handler, _SupportDocStreamHandler)
    ]
    if handlers:
        handler = handlers[0]
        for stale_handler in handlers[1:]:
            package_logger.removeHandler(stale_handler)
    else:
        handler = _SupportDocStreamHandler(stream=sys.stderr)
        package_logger.addHandler(handler)

    handler.setLevel(resolved_level)
    handler.setFormatter(_build_formatter(resolved_format))
    return package_logger


@contextmanager
def request_id_context(request_id: str) -> Iterator[str]:
    """Bind one request ID to the current logging context."""

    token = set_request_id(normalize_request_id(request_id))
    try:
        yield get_request_id() or normalize_request_id(request_id)
    finally:
        reset_request_id(token)


def generate_request_id() -> str:
    """Return a machine-friendly request correlation ID."""

    return uuid4().hex


def normalize_request_id(value: str | None) -> str:
    """Normalize an incoming request ID header or generate a fallback."""

    if value is None:
        return generate_request_id()
    normalized = value.strip()
    if not normalized:
        return generate_request_id()
    return normalized[:128]


def get_request_id() -> str | None:
    """Return the current request correlation ID from context."""

    return _REQUEST_ID_VAR.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Set the current request correlation ID and return the context token."""

    return _REQUEST_ID_VAR.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Reset the request correlation ID to a previous context state."""

    _REQUEST_ID_VAR.reset(token)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: BaseException | tuple[Any, Any, Any] | bool | None = None,
    **fields: Any,
) -> None:
    """Emit a structured, safely-sanitized log event."""

    logger.log(
        level,
        event,
        extra={"event": event, **sanitize_log_fields(fields)},
        exc_info=exc_info,
    )


def sanitize_log_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Redact sensitive values and normalize structured log payloads."""

    sanitized: dict[str, Any] = {}
    for key, value in fields.items():
        normalized_key = _normalize_extra_field_name(str(key))
        sanitized[normalized_key] = _sanitize_log_value(str(key), value)
    return sanitized


def _extract_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_FIELDS or key in {"asctime", "message"}:
            continue
        if key == "event":
            continue
        extracted[key] = _sanitize_log_value(key, value)
    return extracted


def _sanitize_log_value(key: str, value: Any) -> Any:
    normalized_key = key.casefold()
    if normalized_key in _SENSITIVE_FIELD_NAMES:
        return REDACTED_VALUE
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        try:
            return _sanitize_log_value(key, value.model_dump(mode="json"))
        except TypeError:
            return _sanitize_log_value(key, value.model_dump())
    if isinstance(value, Mapping):
        return {str(k): _sanitize_log_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize_log_value(key, item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_extra_field_name(key: str) -> str:
    normalized = key.strip().replace("-", "_")
    if not normalized:
        normalized = "field"
    if normalized in _STANDARD_RECORD_FIELDS:
        return f"field_{normalized}"
    return normalized


def _build_formatter(log_format: str) -> logging.Formatter:
    if log_format == "json":
        return JsonLogFormatter()
    return TextLogFormatter()


def _resolve_log_format(log_format: str | None) -> str:
    candidate = (log_format or os.getenv("LOG_FORMAT", DEFAULT_LOG_FORMAT)).strip().casefold()
    if candidate not in _SUPPORTED_LOG_FORMATS:
        return DEFAULT_LOG_FORMAT
    return candidate


def _resolve_log_level(log_level: str | int | None) -> int:
    candidate = log_level if log_level is not None else os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    if isinstance(candidate, int):
        return candidate
    normalized = str(candidate).strip().upper() or DEFAULT_LOG_LEVEL
    return getattr(logging, normalized, logging.INFO)


def _install_record_factory() -> None:
    global _RECORD_FACTORY_INSTALLED
    if _RECORD_FACTORY_INSTALLED:
        return

    def _supportdoc_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = _BASE_RECORD_FACTORY(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        elif record.request_id is None:
            record.request_id = get_request_id()
        return record

    logging.setLogRecordFactory(_supportdoc_record_factory)
    _RECORD_FACTORY_INSTALLED = True


def _json_default(value: Any) -> Any:
    return _sanitize_log_value("value", value)


def _render_text_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, default=_json_default)
    return str(value)


__all__ = [
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "JsonLogFormatter",
    "PACKAGE_LOGGER_NAME",
    "REDACTED_VALUE",
    "REQUEST_ID_HEADER",
    "TextLogFormatter",
    "configure_logging",
    "generate_request_id",
    "get_request_id",
    "log_event",
    "normalize_request_id",
    "request_id_context",
    "sanitize_log_fields",
]
