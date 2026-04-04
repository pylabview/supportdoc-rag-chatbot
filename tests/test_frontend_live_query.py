from __future__ import annotations

from pathlib import Path

FRONTEND_APP = Path("frontend/src/App.jsx")
FRONTEND_README = Path("frontend/README.md")
SMOKE_SCRIPT = Path("scripts/smoke-browser-demo.sh")


def test_frontend_live_query_wiring_uses_query_and_readyz_routes() -> None:
    content = FRONTEND_APP.read_text(encoding="utf-8")

    assert '"/query"' in content
    assert '"/readyz"' in content
    assert 'method: "POST"' in content
    assert "JSON.stringify({ question })" in content
    assert "result.final_answer" in content
    assert "result.refusal.is_refusal" in content
    assert "Citation markers" in content


def test_frontend_live_query_guard_keeps_submit_disabled_for_empty_input_and_loading() -> None:
    content = FRONTEND_APP.read_text(encoding="utf-8")
    normalized = "".join(content.split())

    assert 'constisSubmitDisabled=uiState==="loading"||!question.trim();' in normalized
    assert "disabled={isSubmitDisabled}" in content
    assert 'setUiState("empty_input")' in content
    assert "Enter a question before submitting." in content


def test_frontend_trust_rendering_distinguishes_supported_answers_from_refusals() -> None:
    content = FRONTEND_APP.read_text(encoding="utf-8")
    normalized = content.casefold()

    assert "renderanswerwithmarkers" in normalized
    assert "citation markers only" in normalized
    assert "reason code" in normalized
    assert "refusals do not carry citations" in normalized
    assert "do not paste secrets" in normalized
    assert "result-state--answer" in content
    assert "result-state--refusal" in content
    assert "citation.source_url" in content
    assert "citation.attribution" in content


def test_frontend_readme_documents_live_backend_wiring_and_readyz_status_probe() -> None:
    content = FRONTEND_README.read_text(encoding="utf-8")

    assert "./scripts/run-api-local.sh" in content
    assert "POST /query" in content
    assert "GET /readyz" in content
    assert "final_answer" in content
    assert "citation markers only" in content
    assert "local Vite dev origins" in content
    assert "Do not paste secrets" in content


def test_browser_demo_smoke_script_builds_and_serves_the_frontend() -> None:
    content = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "npm ci" in content
    assert "npm run build" in content
    assert "python3 -m http.server" in content
    assert "curl -fsS http://127.0.0.1:4173/" in content
