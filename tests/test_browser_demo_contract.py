from __future__ import annotations

from pathlib import Path

CONTRACT_PATH = Path("docs/process/browser_demo_contract.md")


def test_browser_demo_contract_exists_and_covers_current_backend_surface() -> None:
    assert CONTRACT_PATH.is_file()

    content = CONTRACT_PATH.read_text(encoding="utf-8")
    normalized = content.casefold()

    assert "# Browser Demo Contract" in content
    assert "src/supportdoc_rag_chatbot/app/api/routes/query.py" in content
    assert "src/supportdoc_rag_chatbot/app/api/routes/system.py" in content
    assert "docs/contracts/query_response.schema.json" in content
    assert "src/supportdoc_rag_chatbot/app/schemas/trust.py" in content
    assert "post `/query`" in normalized
    assert "get `/readyz`" in normalized
    assert "get `/healthz`" in normalized
    assert 'query_contract != "queryresponse"' in normalized


def test_browser_demo_contract_freezes_required_ui_states_and_evidence_decision() -> None:
    content = CONTRACT_PATH.read_text(encoding="utf-8")
    normalized = content.casefold()

    for state_name in (
        "`empty_input`",
        "`loading`",
        "`supported_answer`",
        "`refusal`",
        "`backend_unavailable`",
    ):
        assert state_name in content

    for field_name in (
        "`final_answer`",
        "`citations`",
        "`refusal.is_refusal`",
        "`refusal.reason_code`",
        "`refusal.message`",
    ):
        assert field_name in content

    assert "citation markers only" in normalized
    assert "does **not** make the markers clickable" in normalized
    assert "does **not** expose evidence text, source url, or attribution" in normalized
    assert "query_response.retrieved_context.example.json" in content
    assert "follow-up" in normalized
    assert "request-scoped evidence payload" in normalized


def test_readme_links_to_browser_demo_contract() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "docs/process/browser_demo_contract.md" in content
    assert "browser-demo integration contract" in content
