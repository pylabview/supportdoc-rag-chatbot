from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SNAPSHOT_ID = "k8s-9e1e32b"
DEFAULT_DATASET_VERSION = "v1"
DEFAULT_DATASET_FILENAME = f"dev_qa.{DEFAULT_SNAPSHOT_ID}.{DEFAULT_DATASET_VERSION}.jsonl"
DEFAULT_METADATA_FILENAME = f"dev_qa.{DEFAULT_SNAPSHOT_ID}.{DEFAULT_DATASET_VERSION}.metadata.json"
DEFAULT_REGISTRY_FILENAME = f"dev_qa.{DEFAULT_SNAPSHOT_ID}.{DEFAULT_DATASET_VERSION}.registry.json"


@dataclass(slots=True)
class DevQAEntry:
    query_id: str
    snapshot_id: str
    question: str
    answerable: bool
    category: str
    tags: list[str]
    doc_ids: list[str]
    expected_section_ids: list[str]
    expected_chunk_ids: list[str]
    notes: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DevQAEntry":
        return cls(
            query_id=str(payload["query_id"]),
            snapshot_id=str(payload["snapshot_id"]),
            question=str(payload["question"]),
            answerable=bool(payload["answerable"]),
            category=str(payload["category"]),
            tags=[str(tag) for tag in payload.get("tags", [])],
            doc_ids=[str(doc_id) for doc_id in payload.get("doc_ids", [])],
            expected_section_ids=[
                str(section_id) for section_id in payload.get("expected_section_ids", [])
            ],
            expected_chunk_ids=[
                str(chunk_id) for chunk_id in payload.get("expected_chunk_ids", [])
            ],
            notes=str(payload.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DevQAMetadata:
    dataset_name: str
    dataset_version: str
    snapshot_id: str
    source_manifest_path: str
    artifact_path: str
    registry_path: str
    row_count: int
    doc_count: int
    section_id_count: int
    chunk_id_count: int
    default_chunking: dict[str, int]
    notes: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DevQAMetadata":
        return cls(
            dataset_name=str(payload["dataset_name"]),
            dataset_version=str(payload["dataset_version"]),
            snapshot_id=str(payload["snapshot_id"]),
            source_manifest_path=str(payload["source_manifest_path"]),
            artifact_path=str(payload["artifact_path"]),
            registry_path=str(payload["registry_path"]),
            row_count=int(payload["row_count"]),
            doc_count=int(payload["doc_count"]),
            section_id_count=int(payload["section_id_count"]),
            chunk_id_count=int(payload["chunk_id_count"]),
            default_chunking={
                str(key): int(value)
                for key, value in dict(payload.get("default_chunking", {})).items()
            },
            notes=str(payload.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceRegistry:
    snapshot_id: str
    source_manifest_path: str
    doc_ids: list[str]
    section_ids: list[str]
    chunk_ids: list[str]
    default_chunking: dict[str, int]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRegistry":
        return cls(
            snapshot_id=str(payload["snapshot_id"]),
            source_manifest_path=str(payload["source_manifest_path"]),
            doc_ids=[str(doc_id) for doc_id in payload.get("doc_ids", [])],
            section_ids=[str(section_id) for section_id in payload.get("section_ids", [])],
            chunk_ids=[str(chunk_id) for chunk_id in payload.get("chunk_ids", [])],
            default_chunking={
                str(key): int(value)
                for key, value in dict(payload.get("default_chunking", {})).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[3]


def default_dev_qa_paths(repo_root: Path | None = None) -> tuple[Path, Path, Path]:
    root = repo_root or repo_root_from_module()
    data_dir = root / "data" / "evaluation"
    return (
        data_dir / DEFAULT_DATASET_FILENAME,
        data_dir / DEFAULT_METADATA_FILENAME,
        data_dir / DEFAULT_REGISTRY_FILENAME,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} on line {line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid JSONL record in {path} on line {line_number}: expected object"
                )
            records.append(record)
    return records


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid JSON payload in {path}: expected object")
    return payload


def load_dev_qa_dataset(path: Path) -> list[DevQAEntry]:
    return [DevQAEntry.from_dict(payload) for payload in _read_jsonl(path)]


def load_default_dev_qa_dataset(repo_root: Path | None = None) -> list[DevQAEntry]:
    dataset_path, _, _ = default_dev_qa_paths(repo_root)
    return load_dev_qa_dataset(dataset_path)


def load_dev_qa_metadata(path: Path) -> DevQAMetadata:
    return DevQAMetadata.from_dict(_load_json_object(path))


def load_default_dev_qa_metadata(repo_root: Path | None = None) -> DevQAMetadata:
    _, metadata_path, _ = default_dev_qa_paths(repo_root)
    return load_dev_qa_metadata(metadata_path)


def load_evidence_registry(path: Path) -> EvidenceRegistry:
    return EvidenceRegistry.from_dict(_load_json_object(path))


def load_default_evidence_registry(repo_root: Path | None = None) -> EvidenceRegistry:
    _, _, registry_path = default_dev_qa_paths(repo_root)
    return load_evidence_registry(registry_path)


def build_evidence_registry_from_artifacts(
    *,
    snapshot_id: str,
    source_manifest_path: str,
    sections_path: Path,
    chunks_path: Path,
    default_chunking: dict[str, int] | None = None,
) -> EvidenceRegistry:
    section_payloads = _read_jsonl(sections_path)
    chunk_payloads = _read_jsonl(chunks_path)

    doc_ids = sorted(
        {
            str(payload["doc_id"])
            for payload in [*section_payloads, *chunk_payloads]
            if "doc_id" in payload
        }
    )
    section_ids = sorted(
        {str(payload["section_id"]) for payload in section_payloads if "section_id" in payload}
    )
    chunk_ids = sorted(
        {str(payload["chunk_id"]) for payload in chunk_payloads if "chunk_id" in payload}
    )

    return EvidenceRegistry(
        snapshot_id=snapshot_id,
        source_manifest_path=source_manifest_path,
        doc_ids=doc_ids,
        section_ids=section_ids,
        chunk_ids=chunk_ids,
        default_chunking=dict(default_chunking or {}),
    )


def validate_dev_qa_dataset(
    *,
    entries: Iterable[DevQAEntry],
    metadata: DevQAMetadata,
    registry: EvidenceRegistry,
) -> None:
    entries = list(entries)
    errors: list[str] = []

    if not entries:
        errors.append("Dataset must contain at least one entry.")

    seen_query_ids: set[str] = set()
    for entry in entries:
        if entry.query_id in seen_query_ids:
            errors.append(f"Duplicate query_id: {entry.query_id}")
        seen_query_ids.add(entry.query_id)

        if entry.snapshot_id != metadata.snapshot_id:
            errors.append(
                f"{entry.query_id}: entry snapshot_id {entry.snapshot_id!r} does not match "
                f"metadata snapshot_id {metadata.snapshot_id!r}"
            )

        if entry.snapshot_id != registry.snapshot_id:
            errors.append(
                f"{entry.query_id}: entry snapshot_id {entry.snapshot_id!r} does not match "
                f"registry snapshot_id {registry.snapshot_id!r}"
            )

        has_expected_evidence = bool(entry.expected_section_ids or entry.expected_chunk_ids)
        if entry.answerable and not has_expected_evidence:
            errors.append(
                f"{entry.query_id}: answerable entries must include at least one section or chunk ID"
            )

        if (not entry.answerable) and has_expected_evidence:
            errors.append(
                f"{entry.query_id}: unanswerable entries must not include section/chunk IDs"
            )

        for doc_id in entry.doc_ids:
            if doc_id not in registry.doc_ids:
                errors.append(f"{entry.query_id}: unknown doc_id {doc_id!r}")

        for section_id in entry.expected_section_ids:
            if section_id not in registry.section_ids:
                errors.append(f"{entry.query_id}: unknown section_id {section_id!r}")

        for chunk_id in entry.expected_chunk_ids:
            if chunk_id not in registry.chunk_ids:
                errors.append(f"{entry.query_id}: unknown chunk_id {chunk_id!r}")

    if metadata.row_count != len(entries):
        errors.append(
            f"Metadata row_count={metadata.row_count} does not match dataset size={len(entries)}"
        )

    if metadata.doc_count != len(registry.doc_ids):
        errors.append(
            f"Metadata doc_count={metadata.doc_count} does not match registry size={len(registry.doc_ids)}"
        )

    if metadata.section_id_count != len(registry.section_ids):
        errors.append("Metadata section_id_count does not match registry section ID count")

    if metadata.chunk_id_count != len(registry.chunk_ids):
        errors.append("Metadata chunk_id_count does not match registry chunk ID count")

    if metadata.default_chunking != registry.default_chunking:
        errors.append("Metadata default_chunking does not match registry default_chunking")

    if errors:
        raise ValueError("\n".join(errors))
