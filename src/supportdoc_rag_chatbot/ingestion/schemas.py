from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ManifestRecord:
    snapshot_id: str
    source_path: str
    source_url: str
    doc_id: str
    language: str
    license: str
    attribution: str
    allowed: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ManifestRecord":
        return cls(
            snapshot_id=str(payload["snapshot_id"]),
            source_path=str(payload["source_path"]),
            source_url=str(payload["source_url"]),
            doc_id=str(payload["doc_id"]),
            language=str(payload.get("language", "en")),
            license=str(payload["license"]),
            attribution=str(payload["attribution"]),
            allowed=bool(payload.get("allowed", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SectionRecord:
    snapshot_id: str
    doc_id: str
    section_id: str
    section_index: int
    doc_title: str
    heading: str | None
    section_path: list[str]
    source_path: str
    source_url: str
    license: str
    attribution: str
    language: str
    start_offset: int
    end_offset: int
    text: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SectionRecord":
        return cls(
            snapshot_id=str(payload["snapshot_id"]),
            doc_id=str(payload["doc_id"]),
            section_id=str(payload["section_id"]),
            section_index=int(payload["section_index"]),
            doc_title=str(payload["doc_title"]),
            heading=str(payload["heading"]) if payload.get("heading") is not None else None,
            section_path=[str(part) for part in payload.get("section_path", [])],
            source_path=str(payload["source_path"]),
            source_url=str(payload["source_url"]),
            license=str(payload["license"]),
            attribution=str(payload["attribution"]),
            language=str(payload.get("language", "en")),
            start_offset=int(payload["start_offset"]),
            end_offset=int(payload["end_offset"]),
            text=str(payload["text"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChunkRecord:
    snapshot_id: str
    doc_id: str
    chunk_id: str
    section_id: str
    section_index: int
    chunk_index: int
    doc_title: str
    section_path: list[str]
    source_path: str
    source_url: str
    license: str
    attribution: str
    language: str
    start_offset: int
    end_offset: int
    token_count: int
    text: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChunkRecord":
        return cls(
            snapshot_id=str(payload["snapshot_id"]),
            doc_id=str(payload["doc_id"]),
            chunk_id=str(payload["chunk_id"]),
            section_id=str(payload["section_id"]),
            section_index=int(payload["section_index"]),
            chunk_index=int(payload["chunk_index"]),
            doc_title=str(payload["doc_title"]),
            section_path=[str(part) for part in payload.get("section_path", [])],
            source_path=str(payload["source_path"]),
            source_url=str(payload["source_url"]),
            license=str(payload["license"]),
            attribution=str(payload["attribution"]),
            language=str(payload.get("language", "en")),
            start_offset=int(payload["start_offset"]),
            end_offset=int(payload["end_offset"]),
            token_count=int(payload["token_count"]),
            text=str(payload["text"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IngestReport:
    snapshot_id: str | None
    manifest_path: str
    sections_path: str
    chunks_path: str
    document_count: int = 0
    section_count: int = 0
    chunk_count: int = 0
    estimated_token_count: int = 0
    empty_section_count: int = 0
    empty_chunk_count: int = 0
    duplicate_section_ids: int = 0
    duplicate_chunk_ids: int = 0
    missing_metadata_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warning_count"] = len(self.warnings)
        payload["error_count"] = len(self.errors)
        return payload
