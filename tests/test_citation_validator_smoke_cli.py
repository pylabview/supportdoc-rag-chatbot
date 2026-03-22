from __future__ import annotations

from pathlib import Path

from supportdoc_rag_chatbot.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSWER_FIXTURE_PATH = REPO_ROOT / "docs/contracts/query_response.answer.example.json"
REFUSAL_FIXTURE_PATH = REPO_ROOT / "docs/contracts/query_response.refusal.example.json"
RETRIEVED_CONTEXT_FIXTURE_PATH = (
    REPO_ROOT / "docs/contracts/query_response.retrieved_context.example.json"
)


def test_smoke_citation_validator_cli_prints_success(capsys) -> None:
    exit_code = main(
        [
            "smoke-citation-validator",
            "--answer-fixture",
            str(ANSWER_FIXTURE_PATH),
            "--refusal-fixture",
            str(REFUSAL_FIXTURE_PATH),
            "--retrieved-context",
            str(RETRIEVED_CONTEXT_FIXTURE_PATH),
        ]
    )

    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Citation validator smoke test" in out
    assert f"answer fixture: {ANSWER_FIXTURE_PATH}" in out
    assert f"refusal fixture: {REFUSAL_FIXTURE_PATH}" in out
    assert f"retrieved context: {RETRIEVED_CONTEXT_FIXTURE_PATH}" in out
    assert "outcome=valid" in out
    assert "chunks=1" in out
    assert "status: ok" in out
