from __future__ import annotations


class QueryPipelineError(RuntimeError):
    """Base error raised when backend query orchestration cannot complete."""

    code = "backend_runtime_error"

    def __init__(self, message: str) -> None:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        super().__init__(normalized)


class QueryPipelineConfigurationError(QueryPipelineError):
    """Raised when backend orchestration is misconfigured."""

    code = "backend_configuration_error"


class QueryPipelineRuntimeError(QueryPipelineError):
    """Raised when backend orchestration fails at runtime."""

    code = "backend_runtime_error"


__all__ = [
    "QueryPipelineConfigurationError",
    "QueryPipelineError",
    "QueryPipelineRuntimeError",
]
