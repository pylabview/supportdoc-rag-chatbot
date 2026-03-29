from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from supportdoc_rag_chatbot.app.api import create_app
from supportdoc_rag_chatbot.app.core.artifact_smoke import build_artifact_smoke_fixture
from supportdoc_rag_chatbot.app.core.local_workflow import evaluate_local_api_readiness
from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode
from supportdoc_rag_chatbot.config import BackendSettings, load_backend_settings


def _artifact_smoke_settings(fixture_dir: Path) -> BackendSettings:
    fixture = build_artifact_smoke_fixture(fixture_dir)
    return BackendSettings(
        app_name="SupportDoc Artifact Smoke API",
        environment="test",
        api_version="9.9.9",
        docs_url="/docs",
        redoc_url="/redoc",
        query_retrieval_mode="artifact",
        query_generation_mode="fixture",
        query_top_k=3,
        query_artifact_chunks_path=str(fixture.chunks_path),
        query_artifact_index_path=str(fixture.index_path),
        query_artifact_index_metadata_path=str(fixture.index_metadata_path),
        query_artifact_row_mapping_path=str(fixture.row_mapping_path),
        query_artifact_embedder_mode="fixture",
        query_artifact_embedder_fixture_path=str(fixture.embedder_fixture_path),
    )


def test_artifact_smoke_fixture_materializes_required_artifacts(tmp_path: Path) -> None:
    fixture = build_artifact_smoke_fixture(tmp_path / "artifact-smoke")

    assert fixture.chunks_path.is_file()
    assert fixture.index_path.is_file()
    assert fixture.index_metadata_path.is_file()
    assert fixture.row_mapping_path.is_file()
    assert fixture.embedder_fixture_path.is_file()
    assert fixture.supported_question == "What is a Pod?"
    assert fixture.refusal_question == "How do I reset my laptop BIOS?"
    assert fixture.chunk_ids == (
        "content-en-docs-concepts-workloads-pods-pods__chunk-0001",
        "content-en-docs-concepts-workloads-pods-pods__chunk-0002",
    )


def test_artifact_mode_local_api_preflight_accepts_override_paths_and_fixture_embedder(
    tmp_path: Path,
) -> None:
    settings = _artifact_smoke_settings(tmp_path)

    report = evaluate_local_api_readiness(settings)

    assert report.mode == "artifact"
    assert report.is_ready is True
    assert report.missing_paths == ()
    assert {check.name for check in report.checks} == {
        "chunks",
        "faiss_index",
        "faiss_index_metadata",
        "faiss_row_mapping",
        "artifact_embedder_fixture",
    }


def test_artifact_mode_api_returns_supported_and_refusal_responses_with_override_paths(
    tmp_path: Path,
) -> None:
    fixture = build_artifact_smoke_fixture(tmp_path / "artifact-api")
    settings = BackendSettings(
        app_name="SupportDoc Artifact Smoke API",
        environment="test",
        api_version="9.9.9",
        docs_url="/docs",
        redoc_url="/redoc",
        query_retrieval_mode="artifact",
        query_generation_mode="fixture",
        query_top_k=3,
        query_artifact_chunks_path=str(fixture.chunks_path),
        query_artifact_index_path=str(fixture.index_path),
        query_artifact_index_metadata_path=str(fixture.index_metadata_path),
        query_artifact_row_mapping_path=str(fixture.row_mapping_path),
        query_artifact_embedder_mode="fixture",
        query_artifact_embedder_fixture_path=str(fixture.embedder_fixture_path),
    )

    with TestClient(create_app(settings=settings)) as client:
        readyz_response = client.get("/readyz")
        assert readyz_response.status_code == 200
        assert readyz_response.json()["status"] == "ready"

        supported_response = client.post("/query", json={"question": "What is a Pod?"})
        assert supported_response.status_code == 200
        supported = QueryResponse.model_validate(supported_response.json())
        assert supported.refusal.is_refusal is False
        assert {citation.chunk_id for citation in supported.citations}.issubset(
            set(fixture.chunk_ids)
        )
        assert supported.citations[0].chunk_id == fixture.chunk_ids[0]

        refusal_response = client.post(
            "/query",
            json={"question": "How do I reset my laptop BIOS?"},
        )
        assert refusal_response.status_code == 200
        refusal = QueryResponse.model_validate(refusal_response.json())
        assert refusal.refusal.is_refusal is True
        assert refusal.refusal.reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
        assert refusal.citations == []


def test_backend_settings_load_artifact_smoke_override_environment() -> None:
    settings = load_backend_settings(
        {
            "SUPPORTDOC_QUERY_RETRIEVAL_MODE": "artifact",
            "SUPPORTDOC_QUERY_GENERATION_MODE": "fixture",
            "SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH": "/tmp/chunks.jsonl",
            "SUPPORTDOC_QUERY_ARTIFACT_INDEX_PATH": "/tmp/chunk_index.faiss",
            "SUPPORTDOC_QUERY_ARTIFACT_INDEX_METADATA_PATH": "/tmp/chunk_index.metadata.json",
            "SUPPORTDOC_QUERY_ARTIFACT_ROW_MAPPING_PATH": "/tmp/chunk_index.row_mapping.json",
            "SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_MODE": "fixture",
            "SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_FIXTURE_PATH": "/tmp/query_embedding_fixture.json",
        }
    )

    assert settings.query_artifact_chunks_path == "/tmp/chunks.jsonl"
    assert settings.query_artifact_index_path == "/tmp/chunk_index.faiss"
    assert settings.query_artifact_index_metadata_path == "/tmp/chunk_index.metadata.json"
    assert settings.query_artifact_row_mapping_path == "/tmp/chunk_index.row_mapping.json"
    assert settings.query_artifact_embedder_mode == "fixture"
    assert settings.query_artifact_embedder_fixture_path == "/tmp/query_embedding_fixture.json"


def test_artifact_smoke_script_has_help_and_uses_artifact_override_path() -> None:
    script = Path("scripts/smoke-artifact-api.sh")
    assert script.is_file()

    help_result = subprocess.run(
        ["bash", str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Usage: ./scripts/smoke-artifact-api.sh" in help_result.stdout
    assert "--port" in help_result.stdout
    assert "--keep-temp" in help_result.stdout
    assert "--extra faiss" in help_result.stdout

    content = script.read_text(encoding="utf-8")
    assert "build_artifact_smoke_fixture" in content
    assert "SUPPORTDOC_LOCAL_API_MODE=artifact" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_MODE=fixture" in content
    assert "QueryResponse.model_validate" in content
    assert "RefusalReasonCode.NO_RELEVANT_DOCS" in content
    assert "Artifact-mode API smoke diagnostics" in content
    assert "trap cleanup EXIT" in content


def test_readme_documents_canonical_artifact_mode_smoke_command() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "### Canonical artifact-mode smoke command" in content
    assert "./scripts/smoke-artifact-api.sh" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_MODE=local|fixture" in content
    assert "no long-running model server or local embedding stack is required" in content
