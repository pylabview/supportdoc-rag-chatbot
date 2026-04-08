from __future__ import annotations

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import supportdoc_rag_chatbot.app.core.query_service as query_service_module
from supportdoc_rag_chatbot.app.api import create_app
from supportdoc_rag_chatbot.app.client import FixtureGenerationClient
from supportdoc_rag_chatbot.app.core import FixtureQueryRetriever
from supportdoc_rag_chatbot.config import BackendSettings, load_backend_settings


def test_config_module_cold_import_succeeds() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from supportdoc_rag_chatbot.config import load_backend_settings; print(load_backend_settings.__name__)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "load_backend_settings"


def test_load_backend_settings_reads_pgvector_and_openai_compatible_env_mapping() -> None:
    settings = load_backend_settings(
        {
            "SUPPORTDOC_DEPLOYMENT_TARGET": "aws",
            "SUPPORTDOC_API_CORS_ALLOWED_ORIGINS": "https://demo.example.test",
            "SUPPORTDOC_QUERY_RETRIEVAL_MODE": "pgvector",
            "SUPPORTDOC_QUERY_PGVECTOR_DSN": "postgresql://demo:demo@db:5432/supportdoc",
            "SUPPORTDOC_QUERY_PGVECTOR_SCHEMA_NAME": "supportdoc_rag",
            "SUPPORTDOC_QUERY_PGVECTOR_RUNTIME_ID": "runtime-001",
            "SUPPORTDOC_QUERY_GENERATION_MODE": "openai_compatible",
            "SUPPORTDOC_QUERY_GENERATION_BASE_URL": "https://model.example.test",
            "SUPPORTDOC_QUERY_GENERATION_MODEL": "demo-model",
        }
    )

    assert settings.deployment_target == "aws"
    assert settings.query_retrieval_mode == "pgvector"
    assert settings.query_pgvector_dsn == "postgresql://demo:demo@db:5432/supportdoc"
    assert settings.query_pgvector_schema_name == "supportdoc_rag"
    assert settings.query_pgvector_runtime_id == "runtime-001"
    assert settings.query_generation_mode == "openai_compatible"
    assert settings.query_generation_base_url == "https://model.example.test"
    assert settings.query_generation_model == "demo-model"


def test_backend_settings_fail_fast_when_pgvector_mode_lacks_database_url() -> None:
    with pytest.raises(ValidationError, match="SUPPORTDOC_QUERY_PGVECTOR_DSN"):
        BackendSettings(
            deployment_target="aws",
            api_cors_allowed_origins=("https://demo.example.test",),
            query_retrieval_mode="pgvector",
            query_generation_mode="fixture",
        )


def test_backend_settings_fail_fast_when_openai_compatible_mode_lacks_model() -> None:
    with pytest.raises(ValidationError, match="SUPPORTDOC_QUERY_GENERATION_MODEL"):
        BackendSettings(
            deployment_target="aws",
            api_cors_allowed_origins=("https://demo.example.test",),
            query_retrieval_mode="fixture",
            query_generation_mode="openai_compatible",
            query_generation_base_url="https://model.example.test",
            query_generation_model=None,
        )


def test_query_path_supports_pgvector_and_openai_modes_without_changing_browser_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_create_query_retriever(*, mode, **kwargs):
        observed["retriever_mode"] = getattr(mode, "value", mode)
        observed["retriever_kwargs"] = kwargs
        return FixtureQueryRetriever()

    def fake_create_generation_client(*, mode, **kwargs):
        observed["generation_mode"] = getattr(mode, "value", mode)
        observed["generation_kwargs"] = kwargs
        return FixtureGenerationClient()

    monkeypatch.setattr(query_service_module, "create_query_retriever", fake_create_query_retriever)
    monkeypatch.setattr(
        query_service_module,
        "create_generation_client",
        fake_create_generation_client,
    )

    settings = BackendSettings(
        deployment_target="aws",
        api_cors_allowed_origins=("https://demo.example.test",),
        query_retrieval_mode="pgvector",
        query_pgvector_dsn="postgresql://demo:demo@db:5432/supportdoc",
        query_generation_mode="openai_compatible",
        query_generation_base_url="https://model.example.test",
        query_generation_model="demo-model",
    )

    with TestClient(create_app(settings=settings)) as client:
        response = client.post("/query", json={"question": "What is a Pod?"})

    assert response.status_code == 200
    assert response.json()["refusal"]["is_refusal"] is False
    assert response.json()["citations"][0]["marker"] == "[1]"
    assert observed == {
        "retriever_mode": "pgvector",
        "retriever_kwargs": {
            "dsn": "postgresql://demo:demo@db:5432/supportdoc",
            "schema_name": "supportdoc_rag",
            "runtime_id": "default",
            "embedder_mode": "local",
            "embedder_fixture_path": None,
        },
        "generation_mode": "openai_compatible",
        "generation_kwargs": {
            "base_url": "https://model.example.test",
            "model": "demo-model",
            "api_key": None,
            "timeout_seconds": 30.0,
        },
    }
