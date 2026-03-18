from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .jsonl import read_jsonl
from .schemas import ChunkRecord, IngestReport, ManifestRecord, SectionRecord

REQUIRED_CHUNK_FIELDS = (
    "source_url",
    "license",
    "attribution",
    "snapshot_id",
    "doc_id",
    "chunk_id",
    "section_path",
    "start_offset",
    "end_offset",
    "token_count",
    "text",
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False


def validate_corpus(
    manifest_records: Iterable[ManifestRecord],
    sections: Iterable[SectionRecord],
    chunks: Iterable[ChunkRecord],
    *,
    manifest_path: Path,
    sections_path: Path,
    chunks_path: Path,
) -> IngestReport:
    manifest_list = list(manifest_records)
    section_list = list(sections)
    chunk_list = list(chunks)

    snapshot_id = manifest_list[0].snapshot_id if manifest_list else None
    warnings: list[str] = []
    errors: list[str] = []

    section_ids_seen: set[str] = set()
    chunk_ids_seen: set[str] = set()
    duplicate_section_ids = 0
    duplicate_chunk_ids = 0
    empty_section_count = 0
    empty_chunk_count = 0
    missing_metadata_count = 0

    for section in section_list:
        if not section.text.strip():
            empty_section_count += 1
            errors.append(f"Empty section text: {section.section_id}")
        if section.section_id in section_ids_seen:
            duplicate_section_ids += 1
            errors.append(f"Duplicate section_id: {section.section_id}")
        section_ids_seen.add(section.section_id)

    for chunk in chunk_list:
        if not chunk.text.strip():
            empty_chunk_count += 1
            errors.append(f"Empty chunk text: {chunk.chunk_id}")
        if chunk.chunk_id in chunk_ids_seen:
            duplicate_chunk_ids += 1
            errors.append(f"Duplicate chunk_id: {chunk.chunk_id}")
        chunk_ids_seen.add(chunk.chunk_id)

        for field_name in REQUIRED_CHUNK_FIELDS:
            value = getattr(chunk, field_name)
            if _is_missing(value):
                missing_metadata_count += 1
                errors.append(f"Missing required metadata '{field_name}' on chunk {chunk.chunk_id}")

        if chunk.start_offset >= chunk.end_offset:
            errors.append(f"Invalid chunk offsets: {chunk.chunk_id}")

    if not manifest_list:
        warnings.append("Manifest was empty.")
    if not section_list:
        warnings.append("No sections were produced.")
    if not chunk_list:
        warnings.append("No chunks were produced.")

    manifest_doc_ids = {record.doc_id for record in manifest_list}
    section_doc_ids = {section.doc_id for section in section_list}
    chunk_doc_ids = {chunk.doc_id for chunk in chunk_list}
    if section_doc_ids - manifest_doc_ids:
        warnings.append("Parsed sections contain doc_ids that were not present in the manifest.")
    if chunk_doc_ids - section_doc_ids:
        warnings.append("Chunks contain doc_ids that were not present in parsed sections.")

    report = IngestReport(
        snapshot_id=snapshot_id,
        manifest_path=str(manifest_path),
        sections_path=str(sections_path),
        chunks_path=str(chunks_path),
        document_count=len(manifest_doc_ids),
        section_count=len(section_list),
        chunk_count=len(chunk_list),
        estimated_token_count=sum(chunk.token_count for chunk in chunk_list),
        empty_section_count=empty_section_count,
        empty_chunk_count=empty_chunk_count,
        duplicate_section_ids=duplicate_section_ids,
        duplicate_chunk_ids=duplicate_chunk_ids,
        missing_metadata_count=missing_metadata_count,
        warnings=warnings,
        errors=errors,
    )
    report.warning_count = len(warnings)
    report.error_count = len(errors)
    return report


def load_manifest_records(path: Path) -> list[ManifestRecord]:
    return [ManifestRecord.from_dict(payload) for payload in read_jsonl(path)]


def load_section_records(path: Path) -> list[SectionRecord]:
    return [SectionRecord.from_dict(payload) for payload in read_jsonl(path)]


def load_chunk_records(path: Path) -> list[ChunkRecord]:
    return [ChunkRecord.from_dict(payload) for payload in read_jsonl(path)]


def write_report(report: IngestReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
