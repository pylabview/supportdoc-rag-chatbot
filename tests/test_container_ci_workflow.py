from __future__ import annotations

from pathlib import Path


def test_container_smoke_workflow_builds_fixture_image_and_probes_health_endpoints() -> None:
    workflow = Path(".github/workflows/container-smoke.yml")
    assert workflow.is_file()

    content = workflow.read_text(encoding="utf-8")
    assert "name: container-smoke" in content
    assert "pull_request:" in content
    assert "docker build -f docker/backend.Dockerfile" in content
    assert "--name supportdoc-api" in content
    assert "SUPPORTDOC_LOCAL_API_MODE=fixture" in content
    assert "SUPPORTDOC_QUERY_GENERATION_MODE=fixture" in content
    assert "http://127.0.0.1:9001/healthz" in content
    assert "http://127.0.0.1:9001/readyz" in content
    assert "docker logs supportdoc-api" in content


def test_container_smoke_workflow_documents_local_equivalent_commands() -> None:
    workflow = Path(".github/workflows/container-smoke.yml")
    content = workflow.read_text(encoding="utf-8")

    assert "Local equivalent:" in content
    assert "docker compose up --build -d" in content
    assert "curl http://127.0.0.1:9001/healthz" in content
