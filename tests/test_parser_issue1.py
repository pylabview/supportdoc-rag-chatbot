from __future__ import annotations

import json
from pathlib import Path

import pytest

from supportdoc_rag_chatbot.ingestion.parse_docs import build_sections_artifact
from supportdoc_rag_chatbot.ingestion.parser import parse_document
from supportdoc_rag_chatbot.ingestion.schemas import ManifestRecord


def _write_manifest(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_parse_markdown_document_builds_section_paths_and_offsets(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    source_path = snapshot_root / "content/en/docs/concepts/pods.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        """---
title: Pods
---
Intro with **bold** text and a [link](https://example.com).

## Lifecycle
Pods move through phases.

### Restart Policy
Containers can restart.

```python
print('hello')
```
""",
        encoding="utf-8",
    )

    record = ManifestRecord(
        snapshot_id="snapshot-001",
        source_path="content/en/docs/concepts/pods.md",
        source_url="https://kubernetes.io/docs/concepts/pods/",
        doc_id="k8s_001",
        language="en",
        license="CC BY 4.0",
        attribution="Kubernetes Documentation © The Kubernetes Authors",
        allowed=True,
    )

    sections = parse_document(record, snapshot_root=snapshot_root)

    assert len(sections) == 3
    assert [section.section_path for section in sections] == [
        ["Pods"],
        ["Pods", "Lifecycle"],
        ["Pods", "Lifecycle", "Restart Policy"],
    ]
    assert sections[0].text == "Intro with bold text and a link."
    assert sections[1].text == "Pods move through phases."
    assert "print('hello')" in sections[2].text
    assert sections[0].start_offset == 0
    assert sections[0].end_offset == len(sections[0].text)
    assert sections[1].start_offset == sections[0].end_offset + 2
    assert sections[2].start_offset == sections[1].end_offset + 2
    assert all(section.text.strip() for section in sections)


def test_parse_html_document_normalizes_text_and_skips_empty_sections(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    source_path = snapshot_root / "content/en/docs/tasks/demo.html"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        """
<html>
  <head><title>Demo Page</title></head>
  <body>
    <p>Overview paragraph.</p>
    <h2>Install</h2>
    <p>Install <strong>kubectl</strong>.</p>
    <h3>Notes</h3>
    <pre><code>kubectl get pods</code></pre>
  </body>
</html>
""",
        encoding="utf-8",
    )

    record = ManifestRecord(
        snapshot_id="snapshot-001",
        source_path="content/en/docs/tasks/demo.html",
        source_url="https://example.invalid/demo",
        doc_id="html_001",
        language="en",
        license="CC BY 4.0",
        attribution="Kubernetes Documentation © The Kubernetes Authors",
        allowed=True,
    )

    sections = parse_document(record, snapshot_root=snapshot_root)

    assert [section.section_path for section in sections] == [
        ["Demo Page"],
        ["Demo Page", "Install"],
        ["Demo Page", "Install", "Notes"],
    ]
    assert sections[0].text == "Overview paragraph."
    assert sections[1].text == "Install kubectl."
    assert sections[2].text == "kubectl get pods"


def test_build_sections_artifact_sorts_manifest_for_deterministic_output(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    (snapshot_root / "content/en/docs/tasks").mkdir(parents=True, exist_ok=True)
    file_a = snapshot_root / "content/en/docs/tasks/a.md"
    file_b = snapshot_root / "content/en/docs/tasks/b.md"
    file_a.write_text("# Alpha\nA body.\n", encoding="utf-8")
    file_b.write_text("# Beta\nB body.\n", encoding="utf-8")

    manifest_path = tmp_path / "source_manifest.jsonl"
    _write_manifest(
        manifest_path,
        [
            {
                "snapshot_id": "snapshot-001",
                "source_path": "content/en/docs/tasks/b.md",
                "source_url": "https://example.invalid/b",
                "doc_id": "doc_b",
                "language": "en",
                "license": "CC BY 4.0",
                "attribution": "Kubernetes Documentation © The Kubernetes Authors",
                "allowed": True,
            },
            {
                "snapshot_id": "snapshot-001",
                "source_path": "content/en/docs/tasks/a.md",
                "source_url": "https://example.invalid/a",
                "doc_id": "doc_a",
                "language": "en",
                "license": "CC BY 4.0",
                "attribution": "Kubernetes Documentation © The Kubernetes Authors",
                "allowed": True,
            },
        ],
    )

    output_path = tmp_path / "sections.jsonl"
    sections = build_sections_artifact(
        manifest_path=manifest_path,
        snapshot_root=snapshot_root,
        output_path=output_path,
    )

    assert [section.doc_id for section in sections] == ["doc_a", "doc_b"]
    written = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [entry["doc_id"] for entry in written] == ["doc_a", "doc_b"]

    rerun_output = tmp_path / "sections-second.jsonl"
    rerun_sections = build_sections_artifact(
        manifest_path=manifest_path,
        snapshot_root=snapshot_root,
        output_path=rerun_output,
    )
    assert [section.to_dict() for section in rerun_sections] == [
        section.to_dict() for section in sections
    ]
    assert rerun_output.read_text(encoding="utf-8") == output_path.read_text(encoding="utf-8")


def test_parse_document_raises_when_no_non_empty_sections(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    source_path = snapshot_root / "content/en/docs/tasks/empty.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("---\ntitle: Empty\n---\n", encoding="utf-8")

    record = ManifestRecord(
        snapshot_id="snapshot-001",
        source_path="content/en/docs/tasks/empty.md",
        source_url="https://example.invalid/empty",
        doc_id="empty_001",
        language="en",
        license="CC BY 4.0",
        attribution="Kubernetes Documentation © The Kubernetes Authors",
        allowed=True,
    )

    with pytest.raises(ValueError, match="no non-empty sections"):
        parse_document(record, snapshot_root=snapshot_root)
