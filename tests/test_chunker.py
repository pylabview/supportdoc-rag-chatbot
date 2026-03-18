from __future__ import annotations

import json
from pathlib import Path

from supportdoc_rag_chatbot.ingestion.chunk_docs import build_chunks_artifact
from supportdoc_rag_chatbot.ingestion.chunker import chunk_section, estimate_token_count
from supportdoc_rag_chatbot.ingestion.schemas import SectionRecord


def make_section(
    *,
    doc_id: str = "k8s_001",
    section_id: str = "k8s_001_sec_01",
    text: str,
    section_path: list[str] | None = None,
    start_offset: int = 0,
    section_index: int = 0,
) -> SectionRecord:
    return SectionRecord(
        snapshot_id="2026-03-01",
        doc_id=doc_id,
        section_id=section_id,
        section_index=section_index,
        doc_title="Pods",
        heading=section_path[-1] if section_path else "Pods",
        section_path=section_path or ["Pods"],
        source_path="content/en/docs/concepts/pods.md",
        source_url="https://kubernetes.io/docs/concepts/pods/",
        license="Apache-2.0",
        attribution="Kubernetes Documentation © The Kubernetes Authors",
        language="en",
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        text=text,
    )


def _write_sections(path: Path, sections: list[SectionRecord]) -> None:
    path.write_text(
        "".join(json.dumps(section.to_dict()) + "\n" for section in sections),
        encoding="utf-8",
    )


def test_chunk_section_respects_token_limits() -> None:
    section = make_section(text="one two three four five six seven eight nine ten")

    chunks = chunk_section(section, max_tokens=4, overlap_tokens=1)

    assert len(chunks) == 3
    assert all(chunk.token_count <= 4 for chunk in chunks)
    assert all(estimate_token_count(chunk.text) == chunk.token_count for chunk in chunks)


def test_chunk_section_applies_overlap_correctly() -> None:
    section = make_section(text="one two three four five six seven eight nine ten")

    chunks = chunk_section(section, max_tokens=4, overlap_tokens=2)

    assert [chunk.text for chunk in chunks] == [
        "one two three four",
        "three four five six",
        "five six seven eight",
        "seven eight nine ten",
    ]


def test_chunk_ids_are_deterministic_and_unique() -> None:
    section = make_section(text="one two three four five six seven eight nine ten")

    first_run = chunk_section(section, max_tokens=4, overlap_tokens=1)
    second_run = chunk_section(section, max_tokens=4, overlap_tokens=1)

    first_ids = [chunk.chunk_id for chunk in first_run]
    second_ids = [chunk.chunk_id for chunk in second_run]

    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))


def test_chunk_section_propagates_required_metadata() -> None:
    section = make_section(
        text="one two three four five six",
        section_path=["Pods", "Lifecycle"],
        start_offset=125,
    )

    chunk = chunk_section(section, max_tokens=6, overlap_tokens=1)[0]

    assert chunk.doc_id == section.doc_id
    assert chunk.section_path == ["Pods", "Lifecycle"]
    assert chunk.source_url == section.source_url
    assert chunk.license == section.license
    assert chunk.snapshot_id == section.snapshot_id
    assert chunk.start_offset == 125
    assert chunk.end_offset == 152
    assert chunk.token_count == 6
    assert chunk.text == section.text


def test_build_chunks_artifact_writes_deterministic_jsonl_output(tmp_path: Path) -> None:
    sections = [
        make_section(
            doc_id="k8s_001",
            section_id="k8s_001_sec_01",
            section_index=0,
            text="one two three four five six seven eight",
            section_path=["Pods"],
            start_offset=0,
        ),
        make_section(
            doc_id="k8s_001",
            section_id="k8s_001_sec_02",
            section_index=1,
            text="nine ten eleven twelve",
            section_path=["Pods", "Lifecycle"],
            start_offset=200,
        ),
    ]
    sections_path = tmp_path / "sections.jsonl"
    output_path = tmp_path / "chunks.jsonl"
    rerun_output_path = tmp_path / "chunks-second.jsonl"
    _write_sections(sections_path, sections)

    chunks = build_chunks_artifact(
        sections_path=sections_path,
        output_path=output_path,
        max_tokens=4,
        overlap_tokens=1,
    )
    rerun_chunks = build_chunks_artifact(
        sections_path=sections_path,
        output_path=rerun_output_path,
        max_tokens=4,
        overlap_tokens=1,
    )

    written = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert len(chunks) == len(written)
    assert [chunk.to_dict() for chunk in chunks] == written
    assert [chunk.to_dict() for chunk in chunks] == [chunk.to_dict() for chunk in rerun_chunks]
    assert output_path.read_text(encoding="utf-8") == rerun_output_path.read_text(encoding="utf-8")
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
