from __future__ import annotations

from pathlib import Path


def test_mvp_readiness_report_exists_and_covers_epic_10_items() -> None:
    report = Path("docs/validation/mvp_readiness.md")
    assert report.is_file()

    content = report.read_text(encoding="utf-8")
    assert "## Overall status" in content
    assert "Fixture-mode API smoke" in content
    assert "Container runtime smoke" in content
    assert "Artifact-mode API smoke" in content
    assert "Final evidence review package" in content
    assert "Evidence correctness pass" in content
    assert "Repo polish / source-of-truth cleanup" in content
    assert "AWS baseline cost/ops notes (#78)" in content
    assert "Container build smoke in CI (#79)" in content
    assert "## Known limitations and deferred scope" in content
    assert "## Closure checklist for Epic 10" in content
    assert "## Epic 10 task map" in content


def test_readme_links_to_final_mvp_readiness_report() -> None:
    readme = Path("README.md")
    content = readme.read_text(encoding="utf-8")

    assert "## 9D. Final MVP readiness report" in content
    assert "docs/validation/mvp_readiness.md" in content
