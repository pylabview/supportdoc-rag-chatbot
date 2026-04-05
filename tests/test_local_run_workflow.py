from __future__ import annotations

from pathlib import Path

README = Path("README.md")
FRONTEND_README = Path("frontend/README.md")
VALIDATION_README = Path("docs/validation/README.md")
SMOKE_SCRIPT = Path("scripts/smoke-browser-demo.sh")


def test_demo_day_quick_start_documents_the_canonical_fixture_first_run() -> None:
    content = README.read_text(encoding="utf-8")

    assert "## 2A. Demo day quick start" in content
    assert "Fixture mode is the canonical first-run path" in content
    assert "Artifact mode is the optional second path" in content
    assert "uv sync --locked --extra dev-tools --extra faiss" in content
    assert "./scripts/run-api-local.sh" in content
    assert "SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh" in content
    assert "npm ci" in content
    assert "npm run dev" in content
    assert "http://127.0.0.1:9001" in content
    assert "http://127.0.0.1:5173" in content
    assert "SUPPORTDOC_LOCAL_API_HOST=127.0.0.1" in content
    assert "SUPPORTDOC_LOCAL_API_PORT=9001" in content
    assert "SUPPORTDOC_LOCAL_API_RELOAD=true|false" in content
    assert "VITE_SUPPORTDOC_API_BASE_URL" in content
    assert "^20.19.0 || >=22.12.0" in content


def test_frontend_readme_matches_the_canonical_fixture_and_artifact_workflow() -> None:
    content = FRONTEND_README.read_text(encoding="utf-8")

    assert "## Canonical first-run path" in content
    assert "fixture mode" in content.casefold()
    assert "SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh" in content
    assert "npm ci" in content
    assert "npm run dev" in content
    assert "http://127.0.0.1:9001" in content
    assert "http://127.0.0.1:5173" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_*" in content
    assert "VITE_SUPPORTDOC_API_BASE_URL" in content


def test_validation_index_points_to_the_demo_day_browser_smoke_path() -> None:
    content = VALIDATION_README.read_text(encoding="utf-8")

    assert "combined fixture-mode browser-demo smoke path" in content
    assert "bash scripts/smoke-browser-demo.sh" in content
    assert "./scripts/run-api-local.sh" in content
    assert "README.md` sections `2A. Demo day quick start` and `7C. Local browser demo`" in content


def test_browser_demo_smoke_script_documents_ports_and_runtime_overrides() -> None:
    content = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "SUPPORTDOC_BROWSER_DEMO_SMOKE_API_HOST" in content
    assert "SUPPORTDOC_BROWSER_DEMO_SMOKE_API_PORT" in content
    assert "SUPPORTDOC_BROWSER_DEMO_SMOKE_FRONTEND_HOST" in content
    assert "SUPPORTDOC_BROWSER_DEMO_SMOKE_FRONTEND_PORT" in content
    assert "SUPPORTDOC_BROWSER_DEMO_SMOKE_TIMEOUT_SECONDS" in content
    assert "Node ^20.19.0 || >=22.12.0" in content
