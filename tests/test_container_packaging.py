from __future__ import annotations

from pathlib import Path


def test_backend_dockerfile_sets_fixture_defaults_and_non_root_runtime() -> None:
    dockerfile = Path("docker/backend.Dockerfile")
    assert dockerfile.is_file()

    content = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:3.13-slim" in content
    assert "SUPPORTDOC_LOCAL_API_MODE=fixture" in content
    assert "uv sync --locked --no-dev --extra embeddings-local" in content
    assert "USER supportdoc" in content
    assert "EXPOSE 9001" in content
    assert "HEALTHCHECK" in content
    assert "./scripts/run-api-local.sh" in content


def test_compose_smoke_service_builds_backend_image_and_maps_local_api_port() -> None:
    compose_file = Path("docker-compose.yml")
    assert compose_file.is_file()

    content = compose_file.read_text(encoding="utf-8")
    assert "supportdoc-api:" in content
    assert "dockerfile: docker/backend.Dockerfile" in content
    assert '"9001:9001"' in content
    assert "SUPPORTDOC_LOCAL_API_MODE: fixture" in content


def test_dockerignore_excludes_local_envs_and_generated_artifacts() -> None:
    dockerignore = Path(".dockerignore")
    assert dockerignore.is_file()

    content = dockerignore.read_text(encoding="utf-8")
    assert ".venv" in content
    assert ".pytest_cache/" in content
    assert "data/processed/" in content
    assert "data/evaluation/runs/" in content


def test_readme_documents_containerized_local_api_smoke_workflow() -> None:
    readme = Path("README.md")
    content = readme.read_text(encoding="utf-8")

    assert "## 7B. Containerized Local API Smoke Workflow" in content
    assert "docker/backend.Dockerfile" in content
    assert "docker compose up --build -d" in content
    assert "Artifact mode inside the container image" in content
    assert "deferred" in content
