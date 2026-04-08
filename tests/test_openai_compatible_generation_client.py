from __future__ import annotations

import json

import httpx

from supportdoc_rag_chatbot.app.client import (
    GenerationFailureCode,
    GenerationRequest,
    OpenAICompatibleGenerationClient,
    parse_query_response_content,
)
from supportdoc_rag_chatbot.app.schemas import build_example_answer_response


def test_openai_compatible_generation_client_builds_chat_request_and_parses_response() -> None:
    observed: dict[str, object] = {}
    answer_payload = build_example_answer_response().model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        observed["method"] = request.method
        observed["path"] = request.url.path
        observed["json"] = json.loads(request.content.decode("utf-8"))
        observed["authorization"] = request.headers.get("authorization")
        observed["timeout"] = request.extensions["timeout"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(answer_payload),
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleGenerationClient(
        base_url="https://model.example.test",
        model="demo-model",
        api_key="secret-token",
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
        "path": "/v1/chat/completions",
        "json": {
            "model": "demo-model",
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
            "temperature": 0.0,
        },
        "authorization": "Bearer secret-token",
        "timeout": {"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0},
    }
    assert result.is_success is True
    assert result.require_response().refusal.is_refusal is False


def test_openai_compatible_generation_client_normalizes_invalid_model_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"final_answer": "missing trust contract fields"}',
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleGenerationClient(
        base_url="https://model.example.test",
        model="demo-model",
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.generate(GenerationRequest(question="What is a Pod?"))
    finally:
        client.close()

    assert result.is_failure is True
    assert result.failure is not None
    assert result.failure.code is GenerationFailureCode.PARSE_ERROR


def test_parse_query_response_content_accepts_fenced_json_payload() -> None:
    payload = build_example_answer_response().model_dump(mode="json")

    parsed = parse_query_response_content(f"```json\n{json.dumps(payload)}\n```")

    assert parsed.refusal.is_refusal is False
    assert parsed.citations[0].marker == "[1]"
