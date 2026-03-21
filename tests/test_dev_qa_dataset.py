from __future__ import annotations

from pathlib import Path

from supportdoc_rag_chatbot.evaluation import (
    DevQAEntry,
    build_evidence_registry_from_artifacts,
    default_dev_qa_paths,
    load_default_dev_qa_dataset,
    load_default_dev_qa_metadata,
    load_default_evidence_registry,
    load_dev_qa_dataset,
    validate_dev_qa_dataset,
)


def test_default_dev_qa_paths_point_at_committed_files() -> None:
    dataset_path, metadata_path, registry_path = default_dev_qa_paths()
    assert dataset_path.is_file()
    assert metadata_path.is_file()
    assert registry_path.is_file()


def test_load_default_dev_qa_dataset_returns_typed_entries() -> None:
    entries = load_default_dev_qa_dataset()
    assert entries
    assert all(isinstance(entry, DevQAEntry) for entry in entries)


def test_default_dev_qa_dataset_validates_against_registry() -> None:
    entries = load_default_dev_qa_dataset()
    metadata = load_default_dev_qa_metadata()
    registry = load_default_evidence_registry()
    validate_dev_qa_dataset(entries=entries, metadata=metadata, registry=registry)


def test_dev_qa_dataset_includes_answerable_and_unanswerable_rows() -> None:
    entries = load_default_dev_qa_dataset()
    assert any(entry.answerable for entry in entries)
    assert any(not entry.answerable for entry in entries)
    assert {entry.category for entry in entries} >= {
        "definition",
        "how-to",
        "troubleshooting",
        "insufficient-evidence",
    }


def test_build_evidence_registry_from_artifacts_round_trips_small_fixture(
    tmp_path: Path,
) -> None:
    sections_path = tmp_path / "sections.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"

    sections_path.write_text(
        "\n".join(
            [
                '{"doc_id":"doc-a","section_id":"doc-a-sec-0000"}',
                '{"doc_id":"doc-b","section_id":"doc-b-sec-0001"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    chunks_path.write_text(
        "\n".join(
            [
                '{"doc_id":"doc-a","chunk_id":"doc-a-chk-0000"}',
                '{"doc_id":"doc-b","chunk_id":"doc-b-chk-0001"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    registry = build_evidence_registry_from_artifacts(
        snapshot_id="snap-1",
        source_manifest_path="data/manifests/source_manifest.jsonl",
        sections_path=sections_path,
        chunks_path=chunks_path,
        default_chunking={"max_tokens": 350, "overlap_tokens": 50},
    )

    assert registry.snapshot_id == "snap-1"
    assert registry.doc_ids == ["doc-a", "doc-b"]
    assert registry.section_ids == ["doc-a-sec-0000", "doc-b-sec-0001"]
    assert registry.chunk_ids == ["doc-a-chk-0000", "doc-b-chk-0001"]


def test_loading_dataset_from_explicit_path_matches_default_loader() -> None:
    dataset_path, _, _ = default_dev_qa_paths()
    default_entries = load_default_dev_qa_dataset()
    explicit_entries = load_dev_qa_dataset(dataset_path)
    assert [entry.to_dict() for entry in default_entries] == [
        entry.to_dict() for entry in explicit_entries
    ]
