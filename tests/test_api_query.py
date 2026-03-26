from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from supportdoc_rag_chatbot.app.client import (
    FixtureGenerationClient,
    GenerationBackendMode,
    GenerationFailure,
    GenerationFailureCode,
    GenerationRequest,
    GenerationResult,
)
from supportdoc_rag_chatbot.app.core import FixtureQueryRetriever
from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode
from supportdoc_rag_chatbot.logging_conf import REQUEST_ID_HEADER


@dataclass(slots=True)
class FailIfCalledGenerationClient:
    backend_mode: GenerationBackendMode = GenerationBackendMode.FIXTURE
    backend_name: str = "fail-if-called"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError(f"generation should not be called for request {request!r}")

    def close(self) -> None:
        return None


@dataclass(slots=True)
class BackendErrorGenerationClient:
    backend_mode: GenerationBackendMode = GenerationBackendMode.FIXTURE
    backend_name: str = "backend-error-fixture"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        del request
        return GenerationResult.from_failure(
            GenerationFailure(
                code=GenerationFailureCode.BACKEND_ERROR,
                message="Simulated backend failure.",
                backend_name=self.backend_name,
                retryable=False,
            )
        )

    def close(self) -> None:
        return None


def test_query_success_path_supports_dependency_overrides_with_fixture_backends(
    api_app: FastAPI,
    override_query_orchestrator,
) -> None:
    override_query_orchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=FixtureGenerationClient(),
    )

    with TestClient(api_app) as client:
        response = client.post(
            "/query",
            json={"question": "What is a Pod?"},
            headers={REQUEST_ID_HEADER: "req-api-query-success-001"},
        )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-api-query-success-001"
    payload = QueryResponse.model_validate(response.json())

    assert payload.refusal.is_refusal is False
    assert payload.citations[0].marker == "[1]"
    assert payload.final_answer.startswith("A Pod is the smallest deployable unit")


def test_query_refusal_path_supports_dependency_overrides_without_generation(
    api_app: FastAPI,
    override_query_orchestrator,
) -> None:
    override_query_orchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=FailIfCalledGenerationClient(),
    )

    with TestClient(api_app) as client:
        response = client.post(
            "/query",
            json={"question": "How do I reset my laptop BIOS?"},
        )

    assert response.status_code == 200
    payload = QueryResponse.model_validate(response.json())

    assert payload.refusal.is_refusal is True
    assert payload.refusal.reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
    assert payload.citations == []


def test_query_invalid_request_returns_stable_422_error_shape(api_app: FastAPI) -> None:
    with TestClient(api_app) as client:
        response = client.post("/query", json={"question": "   "})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "request_validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "type": "value_error",
                    "loc": ["body", "question"],
                    "msg": "Value error, question must not be blank",
                    "input": "   ",
                }
            ],
        }
    }


def test_query_backend_error_returns_json_error_envelope(
    api_app: FastAPI,
    override_query_orchestrator,
) -> None:
    override_query_orchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=BackendErrorGenerationClient(),
    )

    with TestClient(api_app) as client:
        response = client.post(
            "/query",
            json={"question": "What is a Pod?"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "backend_runtime_error",
            "message": (
                "Generation backend failed with backend_error: Simulated backend failure. "
                "(backend=backend-error-fixture)"
            ),
            "details": None,
        }
    }
