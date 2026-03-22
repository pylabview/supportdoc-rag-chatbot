from __future__ import annotations

from pathlib import Path

from supportdoc_rag_chatbot.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs/contracts/query_response.schema.json"
ANSWER_FIXTURE_PATH = REPO_ROOT / "docs/contracts/query_response.answer.example.json"
REFUSAL_FIXTURE_PATH = REPO_ROOT / "docs/contracts/query_response.refusal.example.json"


def test_smoke_trust_schema_cli_prints_success(capsys) -> None:
    exit_code = main(
        [
            "smoke-trust-schema",
            "--schema",
            str(SCHEMA_PATH),
            "--answer-fixture",
            str(ANSWER_FIXTURE_PATH),
            "--refusal-fixture",
            str(REFUSAL_FIXTURE_PATH),
        ]
    )

    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Trust schema smoke test" in out
    assert f"schema: {SCHEMA_PATH}" in out
    assert f"answer fixture: {ANSWER_FIXTURE_PATH}" in out
    assert f"refusal fixture: {REFUSAL_FIXTURE_PATH}" in out
    assert "citations=1" in out
    assert "reason_code=no_relevant_docs" in out
    assert "status: ok" in out
