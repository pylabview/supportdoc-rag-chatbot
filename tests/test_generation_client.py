from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from supportdoc_rag_chatbot.app.client import (
    FixtureGenerationClient,
    GenerationFailureCode,
    GenerationRequest,
    HttpGenerationClient,
)
from supportdoc_rag_chatbot.app.schemas import build_example_answer_response


def test_fixture_generation_client_returns_supported_answer_for_known_question() -> None:
    client = FixtureGenerationClient()

    result = client.generate(GenerationRequest(question="What is a Pod?"))

    assert result.is_success is True
    response = result.require_response()
    assert response.refusal.is_refusal is False
    assert len(response.citations) == 1
    assert response.citations[0].marker == "[1]"


def test_fixture_generation_client_returns_refusal_for_unknown_question() -> None:
    client = FixtureGenerationClient()

    result = client.generate(GenerationRequest(question="How do I reset my laptop BIOS?"))

    assert result.is_success is True
    response = result.require_response()
    assert response.refusal.is_refusal is True
    assert response.citations == []
    assert response.refusal.reason_code == "no_relevant_docs"


def test_fixture_generation_client_normalizes_invalid_fixture_payloads(tmp_path: Path) -> None:
    invalid_fixture_path = tmp_path / "invalid_answer.json"
    invalid_fixture_path.write_text('{"final_answer": "Pods run containers."}', encoding="utf-8")

    client = FixtureGenerationClient(
        answer_fixture_path=invalid_fixture_path,
        answer_questions=("What is a Pod?",),
    )

    result = client.generate(GenerationRequest(question="What is a Pod?"))

    assert result.is_failure is True
    assert result.failure is not None
    assert result.failure.code is GenerationFailureCode.PARSE_ERROR
    assert result.failure.details["path"] == str(invalid_fixture_path)


def test_http_generation_client_builds_request_and_parses_query_response() -> None:
    observed: dict[str, object] = {}
    answer_payload = build_example_answer_response().model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        observed["method"] = request.method
        observed["path"] = request.url.path
        observed["json"] = json.loads(request.content.decode("utf-8"))
        observed["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json=answer_payload)

    client = HttpGenerationClient(
        base_url="https://model.example.test",
        endpoint_path="/v1/generate",
        timeout_seconds=12.5,
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.generate(
            GenerationRequest(
                question="What is a Pod?",
                system_prompt="system prompt",
                user_prompt="user prompt",
                metadata={"request_id": "req-123"},
            )
        )
    finally:
        client.close()

    assert observed == {
        "method": "POST",
        "path": "/v1/generate",
        "json": {
            "question": "What is a Pod?",
            "system_prompt": "system prompt",
            "user_prompt": "user prompt",
            "metadata": {"request_id": "req-123"},
        },
        "timeout": {"connect": 12.5, "read": 12.5, "write": 12.5, "pool": 12.5},
    }
    assert result.is_success is True
    assert result.require_response().refusal.is_refusal is False


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (httpx.ReadTimeout("timed out"), GenerationFailureCode.TIMEOUT),
        (httpx.ConnectError("boom"), GenerationFailureCode.TRANSPORT_ERROR),
    ],
)
def test_http_generation_client_normalizes_timeout_and_transport_errors(
    exception: Exception,
    expected_code: GenerationFailureCode,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    client = HttpGenerationClient(
        base_url="https://model.example.test",
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.generate(GenerationRequest(question="What is a Pod?"))
    finally:
        client.close()

    assert result.is_failure is True
    assert result.failure is not None
    assert result.failure.code is expected_code


def test_http_generation_client_normalizes_backend_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "backend unavailable"})

    client = HttpGenerationClient(
        base_url="https://model.example.test",
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.generate(GenerationRequest(question="What is a Pod?"))
    finally:
        client.close()

    assert result.is_failure is True
    assert result.failure is not None
    assert result.failure.code is GenerationFailureCode.BACKEND_ERROR
    assert result.failure.retryable is True
    assert result.failure.status_code == 503


def test_http_generation_client_normalizes_invalid_response_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"final_answer": "missing trust contract fields"})

    client = HttpGenerationClient(
        base_url="https://model.example.test",
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.generate(GenerationRequest(question="What is a Pod?"))
    finally:
        client.close()

    assert result.is_failure is True
    assert result.failure is not None
    assert result.failure.code is GenerationFailureCode.PARSE_ERROR
