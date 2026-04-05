from __future__ import annotations

from pathlib import Path

NOTE = Path("docs/validation/report_and_aws_handoff_notes.md")


def test_report_ui_handoff_note_exists_and_covers_training_ui_and_aws_direction() -> None:
    assert NOTE.is_file()

    content = NOTE.read_text(encoding="utf-8")
    assert "## Baseline answer for “training process (if applicable)”" in content
    assert "does **not** require fine-tuning" in content
    assert "snapshot -> parse -> chunk -> embed -> index" in content
    assert "React SPA" in content
    assert "FastAPI" in content
    assert "/query" in content
    assert "/healthz" in content
    assert "/readyz" in content
    assert "AWS Amplify Hosting" in content
    assert "ECS Fargate" in content
    assert "browser remains a presentation layer" in content


def test_repo_docs_link_to_report_ui_handoff_note() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    aws_note = Path("docs/architecture/aws_deployment.md").read_text(encoding="utf-8")
    ops_note = Path("docs/ops/cost_and_ops.md").read_text(encoding="utf-8")
    validation_index = Path("docs/validation/README.md").read_text(encoding="utf-8")

    assert "docs/validation/report_and_aws_handoff_notes.md" in readme
    assert "docs/validation/report_and_aws_handoff_notes.md" in aws_note
    assert "React + FastAPI split" in aws_note
    assert "docs/validation/report_and_aws_handoff_notes.md" in ops_note
    assert "local-browser-demo to AWS handoff notes" in ops_note
    assert "docs/validation/report_and_aws_handoff_notes.md" in validation_index
