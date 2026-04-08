from __future__ import annotations

from .factory import create_generation_client
from .fixture import DEFAULT_FIXTURE_SUPPORTED_QUESTIONS, FixtureGenerationClient
from .http import (
    DEFAULT_GENERATION_HTTP_ENDPOINT_PATH,
    DEFAULT_GENERATION_TIMEOUT_SECONDS,
    HttpGenerationClient,
)
from .openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_ENDPOINT_PATH,
    DEFAULT_OPENAI_COMPATIBLE_TEMPERATURE,
    OpenAICompatibleGenerationClient,
    extract_openai_compatible_content,
    parse_query_response_content,
)
from .types import (
    GenerationBackendMode,
    GenerationClient,
    GenerationFailure,
    GenerationFailureCode,
    GenerationRequest,
    GenerationResult,
)

__all__ = [
    "DEFAULT_FIXTURE_SUPPORTED_QUESTIONS",
    "DEFAULT_GENERATION_HTTP_ENDPOINT_PATH",
    "DEFAULT_GENERATION_TIMEOUT_SECONDS",
    "DEFAULT_OPENAI_COMPATIBLE_ENDPOINT_PATH",
    "DEFAULT_OPENAI_COMPATIBLE_TEMPERATURE",
    "FixtureGenerationClient",
    "GenerationBackendMode",
    "GenerationClient",
    "GenerationFailure",
    "GenerationFailureCode",
    "GenerationRequest",
    "GenerationResult",
    "HttpGenerationClient",
    "OpenAICompatibleGenerationClient",
    "create_generation_client",
    "extract_openai_compatible_content",
    "parse_query_response_content",
]
