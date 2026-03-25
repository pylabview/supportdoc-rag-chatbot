from __future__ import annotations

from pathlib import Path
from typing import Iterable

import httpx

from .fixture import FixtureGenerationClient
from .http import (
    DEFAULT_GENERATION_HTTP_ENDPOINT_PATH,
    DEFAULT_GENERATION_TIMEOUT_SECONDS,
    HttpGenerationClient,
)
from .types import GenerationBackendMode, GenerationClient


def create_generation_client(
    *,
    mode: GenerationBackendMode | str,
    answer_fixture_path: Path | None = None,
    refusal_fixture_path: Path | None = None,
    answer_questions: Iterable[str] | None = None,
    base_url: str | None = None,
    endpoint_path: str = DEFAULT_GENERATION_HTTP_ENDPOINT_PATH,
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> GenerationClient:
    """Create the canonical generation client for the requested backend mode."""

    resolved_mode = GenerationBackendMode(mode)
    if resolved_mode is GenerationBackendMode.FIXTURE:
        kwargs: dict[str, object] = {}
        if answer_fixture_path is not None:
            kwargs["answer_fixture_path"] = answer_fixture_path
        if refusal_fixture_path is not None:
            kwargs["refusal_fixture_path"] = refusal_fixture_path
        if answer_questions is not None:
            kwargs["answer_questions"] = tuple(answer_questions)
        return FixtureGenerationClient(**kwargs)

    if base_url is None:
        raise ValueError("base_url is required when mode='http'")
    return HttpGenerationClient(
        base_url=base_url,
        endpoint_path=endpoint_path,
        timeout_seconds=timeout_seconds,
        headers=(headers or {}),
        transport=transport,
    )


__all__ = ["create_generation_client"]
