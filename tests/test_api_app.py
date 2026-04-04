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
    query_retrieval_mode="fixture",
    query_generation_mode="fixture",
)
ARTIFACT_SETTINGS = BackendSettings(
    app_name="SupportDoc Artifact API",
    environment="test",
    api_version="9.9.9",
    docs_url="/docs",
    redoc_url="/redoc",
    query_retrieval_mode="artifact",
    query_generation_mode="fixture",
)


def build_test_client(*, settings: BackendSettings = TEST_SETTINGS) -> TestClient:
    return TestClient(create_app(settings=settings))


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
            "SUPPORTDOC_QUERY_RETRIEVAL_MODE": "artifact",
            "SUPPORTDOC_QUERY_GENERATION_MODE": "http",
            "SUPPORTDOC_QUERY_GENERATION_BASE_URL": "https://model.example.test",
            "SUPPORTDOC_QUERY_GENERATION_TIMEOUT_SECONDS": "12.5",
            "SUPPORTDOC_QUERY_TOP_K": "7",
        }
    )

    assert settings == BackendSettings(
        app_name="Local API",
        environment="dev",
        api_version="1.2.3",
        docs_url="/docs-local",
        redoc_url="/redoc-local",
        query_retrieval_mode="artifact",
        query_generation_mode="http",
        query_generation_base_url="https://model.example.test",
        query_generation_timeout_seconds=12.5,
        query_top_k=7,
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


def test_readyz_allows_local_browser_get_requests_via_cors() -> None:
    with build_test_client() as client:
        response = client.get("/readyz", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_query_preflight_allows_local_browser_post_requests_via_cors() -> None:
    with build_test_client() as client:
        response = client.options(
            "/query",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_query_returns_supported_answer_from_backend_orchestration() -> None:
    with build_test_client() as client:
        response = client.post("/query", json={"question": "What is a Pod?"})

    assert response.status_code == 200
    payload = response.json()
    validated = QueryResponse.model_validate(payload)

    assert validated.refusal.is_refusal is False
    assert validated.citations[0].marker == "[1]"
    assert payload["final_answer"].startswith("A Pod is the smallest deployable unit")


def test_query_returns_canonical_no_relevant_docs_refusal_for_unknown_question() -> None:
    with build_test_client() as client:
        response = client.post("/query", json={"question": "How do I reset my laptop BIOS?"})

    assert response.status_code == 200
    payload = response.json()
    validated = QueryResponse.model_validate(payload)

    assert validated.refusal.is_refusal is True
    assert validated.refusal.reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
    assert validated.citations == []


def test_query_returns_json_config_error_when_artifact_retrieval_is_enabled_without_artifacts() -> (
    None
):
    with build_test_client(settings=ARTIFACT_SETTINGS) as client:
        response = client.post("/query", json={"question": "What is a Pod?"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "backend_configuration_error"
    assert "chunk_index.metadata.json" in response.json()["error"]["message"]


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
