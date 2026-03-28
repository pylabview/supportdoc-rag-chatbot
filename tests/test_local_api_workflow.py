from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from supportdoc_rag_chatbot.app.api import create_app
from supportdoc_rag_chatbot.app.client import GenerationBackendMode
from supportdoc_rag_chatbot.app.core import (
    LocalWorkflowError,
    RetrievalBackendMode,
    ensure_local_api_ready,
    evaluate_local_api_readiness,
)
from supportdoc_rag_chatbot.config import BackendSettings

FIXTURE_SETTINGS = BackendSettings(
    query_retrieval_mode=RetrievalBackendMode.FIXTURE,
    query_generation_mode=GenerationBackendMode.FIXTURE,
)
ARTIFACT_SETTINGS = BackendSettings(
    query_retrieval_mode=RetrievalBackendMode.ARTIFACT,
    query_generation_mode=GenerationBackendMode.FIXTURE,
)


def test_fixture_mode_local_smoke_api_returns_health_ready_and_query() -> None:
    with TestClient(create_app(settings=FIXTURE_SETTINGS)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}

        readyz_response = client.get("/readyz")
        assert readyz_response.status_code == 200
        assert readyz_response.json()["status"] == "ready"

        query_response = client.post("/query", json={"question": "What is a Pod?"})
        assert query_response.status_code == 200
        payload = query_response.json()
        assert payload["refusal"]["is_refusal"] is False
        assert payload["citations"][0]["marker"] == "[1]"


def test_artifact_mode_preflight_reports_missing_files_from_clean_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    report = evaluate_local_api_readiness(ARTIFACT_SETTINGS)

    assert report.mode == "artifact"
    assert report.is_ready is False
    assert report.missing_paths


def test_artifact_mode_preflight_fails_fast_with_clear_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(LocalWorkflowError, match="SUPPORTDOC_QUERY_RETRIEVAL_MODE=fixture"):
        ensure_local_api_ready(ARTIFACT_SETTINGS)


def test_http_generation_mode_requires_base_url() -> None:
    settings = BackendSettings(
        query_retrieval_mode=RetrievalBackendMode.FIXTURE,
        query_generation_mode=GenerationBackendMode.HTTP,
        query_generation_base_url=None,
    )

    with pytest.raises(LocalWorkflowError, match="SUPPORTDOC_QUERY_GENERATION_BASE_URL"):
        ensure_local_api_ready(settings)


def test_run_api_local_script_exists() -> None:
    assert Path("scripts/run-api-local.sh").is_file()
