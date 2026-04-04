from __future__ import annotations

from pathlib import Path

FRONTEND_APP = Path("frontend/src/App.jsx")
FRONTEND_README = Path("frontend/README.md")


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


def test_frontend_readme_documents_live_backend_wiring_and_readyz_status_probe() -> None:
    content = FRONTEND_README.read_text(encoding="utf-8")

    assert "./scripts/run-api-local.sh" in content
    assert "POST /query" in content
    assert "GET /readyz" in content
    assert "final_answer" in content
    assert "citation markers only" in content
    assert "local Vite dev origins" in content
