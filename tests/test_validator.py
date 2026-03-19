from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from supportdoc_rag_chatbot.ingestion.validate_corpus import main as validate_corpus_main
from supportdoc_rag_chatbot.ingestion.validator import build_ingest_report


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _make_manifest(doc_id: str = "k8s_001") -> list[dict[str, object]]:
    return [
        {
            "snapshot_id": "2026-03-01",
            "source_path": f"content/en/docs/{doc_id}.md",
            "source_url": f"https://kubernetes.io/docs/{doc_id}/",
            "doc_id": doc_id,
            "language": "en",
            "license": "CC BY 4.0",
            "attribution": "Kubernetes Documentation © The Kubernetes Authors",
            "allowed": True,
        }
    ]


def _make_sections(doc_id: str = "k8s_001") -> list[dict[str, object]]:
    return [
        {
            "snapshot_id": "2026-03-01",
            "doc_id": doc_id,
            "section_id": f"{doc_id}_sec_01",
            "section_index": 0,
            "doc_title": "Pods",
            "heading": "Pods",
            "section_path": ["Pods"],
            "source_path": f"content/en/docs/{doc_id}.md",
            "source_url": f"https://kubernetes.io/docs/{doc_id}/",
            "license": "CC BY 4.0",
            "attribution": "Kubernetes Documentation © The Kubernetes Authors",
            "language": "en",
            "start_offset": 0,
            "end_offset": 23,
            "text": "Pods are the smallest unit.",
        }
    ]


def _make_chunks(doc_id: str = "k8s_001") -> list[dict[str, object]]:
    return [
        {
            "snapshot_id": "2026-03-01",
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}_chunk_a",
            "section_id": f"{doc_id}_sec_01",
            "section_index": 0,
            "chunk_index": 0,
            "doc_title": "Pods",
            "section_path": ["Pods"],
            "source_path": f"content/en/docs/{doc_id}.md",
            "source_url": f"https://kubernetes.io/docs/{doc_id}/",
            "license": "CC BY 4.0",
            "attribution": "Kubernetes Documentation © The Kubernetes Authors",
            "language": "en",
            "start_offset": 0,
            "end_offset": 10,
            "token_count": 2,
            "text": "Pods are",
        },
        {
            "snapshot_id": "2026-03-01",
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}_chunk_b",
            "section_id": f"{doc_id}_sec_01",
            "section_index": 0,
            "chunk_index": 1,
            "doc_title": "Pods",
            "section_path": ["Pods"],
            "source_path": f"content/en/docs/{doc_id}.md",
            "source_url": f"https://kubernetes.io/docs/{doc_id}/",
            "license": "CC BY 4.0",
            "attribution": "Kubernetes Documentation © The Kubernetes Authors",
            "language": "en",
            "start_offset": 11,
            "end_offset": 23,
            "token_count": 3,
            "text": "the smallest unit",
        },
    ]


def test_build_ingest_report_writes_report_and_counts_match_artifacts(tmp_path: Path) -> None:
    manifest_path = tmp_path / "source_manifest.jsonl"
    sections_path = tmp_path / "sections.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"
    report_path = tmp_path / "ingest_report.json"

    _write_jsonl(manifest_path, _make_manifest())
    _write_jsonl(sections_path, _make_sections())
    _write_jsonl(chunks_path, _make_chunks())

    report = build_ingest_report(
        manifest_path=manifest_path,
        sections_path=sections_path,
        chunks_path=chunks_path,
        output_path=report_path,
    )

    written = json.loads(report_path.read_text(encoding="utf-8"))

    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.document_count == 1
    assert report.section_count == 1
    assert report.chunk_count == 2
    assert report.estimated_token_count == 5
    assert written["document_count"] == 1
    assert written["section_count"] == 1
    assert written["chunk_count"] == 2
    assert written["estimated_token_count"] == 5
    assert written["errors"] == []
    assert written["warnings"] == []


def test_build_ingest_report_captures_empty_chunks_duplicates_and_missing_metadata(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "source_manifest.jsonl"
    sections_path = tmp_path / "sections.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"
    report_path = tmp_path / "ingest_report.json"

    _write_jsonl(manifest_path, _make_manifest())
    _write_jsonl(sections_path, _make_sections())
    _write_jsonl(
        chunks_path,
        [
            {
                **_make_chunks()[0],
                "chunk_id": "dup_chunk",
                "text": "",
            },
            {
                **_make_chunks()[1],
                "chunk_id": "dup_chunk",
                "license": "",
                "token_count": 3,
            },
            {
                **{key: value for key, value in _make_chunks()[1].items() if key != "token_count"},
                "chunk_id": "missing_meta_chunk",
                "section_path": [],
            },
        ],
    )

    report = build_ingest_report(
        manifest_path=manifest_path,
        sections_path=sections_path,
        chunks_path=chunks_path,
        output_path=report_path,
    )

    assert report_path.exists()
    assert report.chunk_count == 3
    assert report.empty_chunk_count == 1
    assert report.duplicate_chunk_ids == 1
    assert report.missing_metadata_count >= 4
    assert any("Duplicate chunk_id: dup_chunk" in error for error in report.errors)
    assert any("Empty chunk text: dup_chunk" in error for error in report.errors)
    assert any(
        "Missing required metadata 'license' on chunk dup_chunk" in error for error in report.errors
    )
    assert any(
        "Missing required metadata 'section_path' on chunk missing_meta_chunk" in error
        for error in report.errors
    )
    assert any(
        "Missing required metadata 'token_count' on chunk missing_meta_chunk" in error
        for error in report.errors
    )


@pytest.mark.parametrize("allow_errors", [False, True])
def test_validate_corpus_cli_writes_report_and_controls_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow_errors: bool,
) -> None:
    manifest_path = tmp_path / "source_manifest.jsonl"
    sections_path = tmp_path / "sections.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"
    report_path = tmp_path / "ingest_report.json"

    _write_jsonl(manifest_path, _make_manifest())
    _write_jsonl(sections_path, _make_sections())
    invalid_chunk = _make_chunks()[0] | {"text": ""}
    _write_jsonl(chunks_path, [invalid_chunk])

    argv = [
        "validate_corpus",
        "--manifest",
        str(manifest_path),
        "--sections",
        str(sections_path),
        "--chunks",
        str(chunks_path),
        "--report-out",
        str(report_path),
    ]
    if allow_errors:
        argv.append("--allow-errors")

    monkeypatch.setattr(sys, "argv", argv)

    if allow_errors:
        validate_corpus_main()
    else:
        with pytest.raises(SystemExit, match="1"):
            validate_corpus_main()

    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["error_count"] >= 1
    assert any("Empty chunk text" in error for error in written["errors"])
