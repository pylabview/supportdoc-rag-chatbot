from __future__ import annotations

import pytest

from supportdoc_rag_chatbot.app.client import (
    FixtureGenerationClient,
    GenerationBackendMode,
    GenerationRequest,
    HttpGenerationClient,
    create_generation_client,
)


def test_create_generation_client_fixture_mode_boots_local_fixture_backend() -> None:
    client = create_generation_client(mode="fixture")

    assert isinstance(client, FixtureGenerationClient)
    assert client.backend_mode is GenerationBackendMode.FIXTURE

    result = client.generate(GenerationRequest(question="What is a Pod?"))
    assert result.is_success is True
    assert result.require_response().refusal.is_refusal is False


def test_create_generation_client_http_mode_requires_base_url() -> None:
    with pytest.raises(ValueError, match="base_url is required when mode='http'"):
        create_generation_client(mode="http")


def test_create_generation_client_http_mode_returns_http_client() -> None:
    client = create_generation_client(mode="http", base_url="https://model.example.test")
    try:
        assert isinstance(client, HttpGenerationClient)
        assert client.backend_mode is GenerationBackendMode.HTTP
    finally:
        client.close()
