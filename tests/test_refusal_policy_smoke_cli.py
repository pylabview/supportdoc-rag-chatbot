from __future__ import annotations

from pathlib import Path

from supportdoc_rag_chatbot.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "src/supportdoc_rag_chatbot/resources/default_config.yaml"


def test_smoke_retrieval_sufficiency_cli_prints_success(capsys) -> None:
    exit_code = main(
        [
            "smoke-retrieval-sufficiency",
            "--config",
            str(CONFIG_PATH),
        ]
    )

    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Retrieval sufficiency smoke test" in out
    assert f"config: {CONFIG_PATH}" in out
    assert "full answer case: allow_full_answer" in out
    assert "thin answer case: allow_thin_answer" in out
    assert "no-hit case: refuse_no_relevant_docs" in out
    assert "insufficient-evidence case: refuse_insufficient_evidence" in out
    assert "status: ok" in out
