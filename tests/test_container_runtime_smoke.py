from __future__ import annotations

import subprocess
from pathlib import Path


def test_container_runtime_smoke_script_has_help_and_primary_docker_run_path() -> None:
    script = Path("scripts/smoke-container-runtime.sh")
    assert script.is_file()

    help_result = subprocess.run(
        ["bash", str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Usage: ./scripts/smoke-container-runtime.sh" in help_result.stdout
    assert "--skip-build" in help_result.stdout
    assert "--host-port" in help_result.stdout

    content = script.read_text(encoding="utf-8")
    assert "docker build -f docker/backend.Dockerfile" in content
    assert "docker run -d --rm" in content
    assert "SUPPORTDOC_LOCAL_API_MODE=fixture" in content
    assert "SUPPORTDOC_QUERY_GENERATION_MODE=fixture" in content
    assert "wait_for_container_health" in content
    assert '"/healthz"' in content
    assert '"/readyz"' in content
    assert "What is a Pod?" in content
    assert "How do I reset my laptop BIOS?" in content


def test_container_runtime_smoke_script_validates_query_contract_and_failure_diagnostics() -> None:
    content = Path("scripts/smoke-container-runtime.sh").read_text(encoding="utf-8")

    assert "QueryResponse.model_validate" in content
    assert "RefusalReasonCode.NO_RELEVANT_DOCS" in content
    assert "docker inspect" in content
    assert "docker logs" in content
    assert "trap cleanup EXIT" in content
    assert "docker rm -f" in content


def test_readme_documents_canonical_container_runtime_smoke_command() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "### Canonical runtime smoke command" in content
    assert "./scripts/smoke-container-runtime.sh" in content
    assert "CI build smoke proves" in content
    assert "docker run" in content
    assert "fixture-mode only" in content
    assert "`docker compose` remains optional" in content
