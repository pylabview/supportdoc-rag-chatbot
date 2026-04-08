from __future__ import annotations

import subprocess
from pathlib import Path


def test_cloud_runtime_smoke_script_has_help_and_cloud_mode_env_contract() -> None:
    script = Path("scripts/smoke-cloud-runtime.sh")
    assert script.is_file()

    help_result = subprocess.run(
        ["bash", str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Usage: ./scripts/smoke-cloud-runtime.sh" in help_result.stdout
    assert "--database-url" in help_result.stdout
    assert "--generation-base-url" in help_result.stdout
    assert "--generation-model" in help_result.stdout
    assert "--skip-promotion" in help_result.stdout

    content = script.read_text(encoding="utf-8")
    assert "promote-pgvector-runtime" in content
    assert "docker build -f docker/backend.Dockerfile" in content
    assert "docker run -d --rm" in content
    assert "SUPPORTDOC_QUERY_RETRIEVAL_MODE=pgvector" in content
    assert "SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible" in content
    assert "SUPPORTDOC_QUERY_PGVECTOR_DSN" in content
    assert "SUPPORTDOC_QUERY_GENERATION_MODEL" in content
    assert "normalize_container_url" in content
    assert "host.docker.internal" in content
    assert "wait_for_container_health" in content
    assert '"/healthz"' in content
    assert '"/readyz"' in content
    assert "What is a Pod?" in content
