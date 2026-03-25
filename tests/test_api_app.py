from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from supportdoc_rag_chatbot.app.api import app, create_app
from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode
from supportdoc_rag_chatbot.config import BackendSettings, load_backend_settings

TEST_SETTINGS = BackendSettings(
    app_name="SupportDoc Test API",
    environment="test",
    api_version="9.9.9",
    docs_url="/docs",
    redoc_url="/redoc",
)


def build_test_client() -> TestClient:
    return TestClient(create_app(settings=TEST_SETTINGS))


def test_module_exports_bootable_fastapi_apps() -> None:
    assert isinstance(app, FastAPI)
    assert isinstance(create_app(), FastAPI)


def test_load_backend_settings_reads_env_mapping() -> None:
    settings = load_backend_settings(
        {
            "SUPPORTDOC_API_TITLE": "Local API",
            "SUPPORTDOC_ENV": "dev",
            "SUPPORTDOC_API_VERSION": "1.2.3",
            "SUPPORTDOC_API_DOCS_URL": "/docs-local",
            "SUPPORTDOC_API_REDOC_URL": "/redoc-local",
        }
    )

    assert settings == BackendSettings(
        app_name="Local API",
        environment="dev",
        api_version="1.2.3",
        docs_url="/docs-local",
        redoc_url="/redoc-local",
    )


def test_healthz_returns_ok_json() -> None:
    with build_test_client() as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_deterministic_json_without_external_dependencies() -> None:
    with build_test_client() as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "SupportDoc Test API",
        "environment": "test",
        "version": "9.9.9",
        "query_contract": "QueryResponse",
    }


def test_query_returns_canonical_query_response_placeholder() -> None:
    with build_test_client() as client:
        response = client.post("/query", json={"question": "What is a Pod?"})

    assert response.status_code == 200
    payload = response.json()
    validated = QueryResponse.model_validate(payload)

    assert validated.refusal.is_refusal is True
    assert validated.refusal.reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
    assert validated.citations == []
    assert payload["final_answer"] == "I can’t answer that from the approved support corpus."


def test_query_validation_errors_return_json_error_response() -> None:
    with build_test_client() as client:
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


def test_http_errors_use_json_error_response_envelope() -> None:
    with build_test_client() as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "http_404",
            "message": "Not Found",
            "details": None,
        }
    }
