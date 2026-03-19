from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

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


def _field(record: object, field_name: str, default: object | None = None) -> object | None:
    if isinstance(record, dict):
        return record.get(field_name, default)
    return getattr(record, field_name, default)


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _record_identifier(record: object, field_name: str, *, fallback_prefix: str, index: int) -> str:
    value = _field(record, field_name)
    if value is None:
        return f"<{fallback_prefix}-{index}>"
    text = str(value).strip()
    if not text:
        return f"<{fallback_prefix}-{index}>"
    return text


def validate_corpus(
    manifest_records: Iterable[ManifestRecord | dict[str, Any]],
    sections: Iterable[SectionRecord | dict[str, Any]],
    chunks: Iterable[ChunkRecord | dict[str, Any]],
    *,
    manifest_path: Path,
    sections_path: Path,
    chunks_path: Path,
) -> IngestReport:
    manifest_list = list(manifest_records)
    section_list = list(sections)
    chunk_list = list(chunks)

    snapshot_id_value = _field(manifest_list[0], "snapshot_id") if manifest_list else None
    snapshot_id = str(snapshot_id_value) if snapshot_id_value is not None else None
    warnings: list[str] = []
    errors: list[str] = []

    section_ids_seen: set[str] = set()
    chunk_ids_seen: set[str] = set()
    duplicate_section_ids = 0
    duplicate_chunk_ids = 0
    empty_section_count = 0
    empty_chunk_count = 0
    missing_metadata_count = 0

    for index, section in enumerate(section_list, start=1):
        section_id = _record_identifier(
            section,
            "section_id",
            fallback_prefix="missing-section-id",
            index=index,
        )
        section_text = str(_field(section, "text", "") or "")
        if not section_text.strip():
            empty_section_count += 1
            errors.append(f"Empty section text: {section_id}")
        if section_id in section_ids_seen:
            duplicate_section_ids += 1
            errors.append(f"Duplicate section_id: {section_id}")
        section_ids_seen.add(section_id)

    for index, chunk in enumerate(chunk_list, start=1):
        chunk_id = _record_identifier(
            chunk,
            "chunk_id",
            fallback_prefix="missing-chunk-id",
            index=index,
        )
        chunk_text = str(_field(chunk, "text", "") or "")
        if not chunk_text.strip():
            empty_chunk_count += 1
            errors.append(f"Empty chunk text: {chunk_id}")
        if chunk_id in chunk_ids_seen:
            duplicate_chunk_ids += 1
            errors.append(f"Duplicate chunk_id: {chunk_id}")
        chunk_ids_seen.add(chunk_id)

        for field_name in REQUIRED_CHUNK_FIELDS:
            value = _field(chunk, field_name)
            if _is_missing(value):
                missing_metadata_count += 1
                errors.append(f"Missing required metadata '{field_name}' on chunk {chunk_id}")

        start_offset = _safe_int(_field(chunk, "start_offset"))
        end_offset = _safe_int(_field(chunk, "end_offset"))
        if start_offset is not None and end_offset is not None and start_offset >= end_offset:
            errors.append(f"Invalid chunk offsets: {chunk_id}")

    if not manifest_list:
        warnings.append("Manifest was empty.")
    if not section_list:
        warnings.append("No sections were produced.")
    if not chunk_list:
        warnings.append("No chunks were produced.")

    manifest_doc_ids = {
        str(doc_id).strip()
        for record in manifest_list
        if (doc_id := _field(record, "doc_id")) is not None and str(doc_id).strip()
    }
    section_doc_ids = {
        str(doc_id).strip()
        for section in section_list
        if (doc_id := _field(section, "doc_id")) is not None and str(doc_id).strip()
    }
    chunk_doc_ids = {
        str(doc_id).strip()
        for chunk in chunk_list
        if (doc_id := _field(chunk, "doc_id")) is not None and str(doc_id).strip()
    }
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
        estimated_token_count=sum(
            _safe_int(_field(chunk, "token_count")) or 0 for chunk in chunk_list
        ),
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


def build_ingest_report(
    *,
    manifest_path: Path,
    sections_path: Path,
    chunks_path: Path,
    output_path: Path,
) -> IngestReport:
    report = validate_corpus(
        read_jsonl(manifest_path),
        read_jsonl(sections_path),
        read_jsonl(chunks_path),
        manifest_path=manifest_path,
        sections_path=sections_path,
        chunks_path=chunks_path,
    )
    write_report(report, output_path)
    return report


def write_report(report: IngestReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
