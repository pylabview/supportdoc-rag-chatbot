from __future__ import annotations

import tomllib
from pathlib import Path

PLATFORM_NOTES = Path("docs/validation/local_workflow_platforms.md")


def test_local_platform_notes_cover_target_machines_and_baselines() -> None:
    assert PLATFORM_NOTES.is_file()

    content = PLATFORM_NOTES.read_text(encoding="utf-8")
    normalized = content.casefold()

    assert "macOS arm64" in content
    assert "Pop!_OS x86_64" in content
    assert "Python 3.13" in content
    assert "^20.19.0 || >=22.12.0" in content
    assert "./scripts/run-api-local.sh" in content
    assert "npm install" in content
    assert "npm run dev" in content
    assert "fixture-mode" in normalized
    assert "artifact mode" in normalized
    assert "readyz" in normalized


def test_local_platform_notes_capture_artifact_prerequisites_and_vllm_scope() -> None:
    content = PLATFORM_NOTES.read_text(encoding="utf-8")
    normalized = content.casefold()

    assert "SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh" in content
    assert "data/processed/chunks.jsonl" in content
    assert "chunk_index.faiss" in content
    assert "chunk_index.metadata.json" in content
    assert "chunk_index.row_mapping.json" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_INDEX_PATH" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_INDEX_METADATA_PATH" in content
    assert "SUPPORTDOC_QUERY_ARTIFACT_ROW_MAPPING_PATH" in content
    assert "llm-vllm" in content
    assert "linux-only" in normalized
    assert (
        "does **not** require `llm-vllm`" in content
        or "does **not** require `llm-vllm`" in content.replace("'", "`")
    )


def test_repo_metadata_and_docs_align_on_python_baseline_and_platform_note_links() -> None:
    python_version = Path(".python-version").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")
    frontend_readme = Path("frontend/README.md").read_text(encoding="utf-8")
    validation_readme = Path("docs/validation/README.md").read_text(encoding="utf-8")

    assert python_version == "3.13"
    assert pyproject["project"]["requires-python"] == ">=3.13,<3.14"
    assert "docs/validation/local_workflow_platforms.md" in readme
    assert "docs/validation/local_workflow_platforms.md" in frontend_readme
    assert "docs/validation/local_workflow_platforms.md" in validation_readme
    assert "Python 3.13" in readme
    assert "Python 3.13" in frontend_readme
