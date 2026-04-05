from __future__ import annotations

from pathlib import Path

CHECKLIST = Path("docs/validation/browser_smoke_checklist.md")
VALIDATION_INDEX = Path("docs/validation/README.md")
ROOT_README = Path("README.md")
FRONTEND_README = Path("frontend/README.md")
PLATFORM_NOTES = Path("docs/validation/local_workflow_platforms.md")


def test_browser_smoke_checklist_covers_canonical_fixture_mode_and_manual_cases() -> None:
    assert CHECKLIST.is_file()

    content = CHECKLIST.read_text(encoding="utf-8")
    normalized = content.casefold()

    assert "canonical demo path" in normalized
    assert "fixture mode" in normalized
    assert "./scripts/run-api-local.sh" in content
    assert "bash scripts/smoke-browser-demo.sh" in content
    assert "npm ci" in content
    assert "npm run dev" in content
    assert "What is a Pod?" in content
    assert "How do I reset my laptop BIOS?" in content
    assert "[1]" in content
    assert "no_relevant_docs" in content
    assert "backend unavailable" in normalized
    assert "empty input" in normalized or "empty-input" in normalized


def test_browser_smoke_checklist_captures_long_answer_override_and_demo_notes() -> None:
    content = CHECKLIST.read_text(encoding="utf-8")
    normalized = content.casefold()

    assert "multi-citation visual check" in normalized
    assert "temporary long-answer / multi-citation response override" in normalized
    assert "one-shot visual override" in normalized
    assert "visual-only" in normalized or "ui-only" in normalized
    assert "window.fetch" in content
    assert "[2]" in content
    assert "[3]" in content
    assert "citation markers only" in normalized
    assert (
        "does not keep stale answer text" in normalized
        or "does not keep stale supported/refusal output on screen" in normalized
    )
    assert "short demo sequence for presentation use" in normalized or "demo sequence" in normalized
    assert "simple result-capture template" in normalized or "reusable demo notes" in normalized
    assert "macos arm64 / pop!_os x86_64" in normalized


def test_repo_docs_link_to_the_manual_browser_smoke_checklist() -> None:
    validation_content = VALIDATION_INDEX.read_text(encoding="utf-8")
    readme_content = ROOT_README.read_text(encoding="utf-8")
    frontend_content = FRONTEND_README.read_text(encoding="utf-8")
    platform_notes = PLATFORM_NOTES.read_text(encoding="utf-8")

    assert "docs/validation/browser_smoke_checklist.md" in validation_content
    assert "supported answer in canonical fixture mode" in validation_content
    assert "docs/validation/browser_smoke_checklist.md" in readme_content
    assert "docs/validation/browser_smoke_checklist.md" in frontend_content
    assert "does send live `POST /query` requests" in platform_notes
    assert "does **not** send live `POST /query` requests yet" not in platform_notes
