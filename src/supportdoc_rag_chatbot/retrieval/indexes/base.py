from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

INDEX_ARTIFACT_VERSION = "v1"


@dataclass(slots=True)
class DenseSearchResult:
    chunk_id: str
    score: float
    rank: int
    row_index: int
    source_chunks_path: str


@dataclass(slots=True)
class DenseIndexMetadata:
    artifact_version: str
    backend_name: str
    metric: str
    vector_dimension: int
    row_count: int
    embedding_model_name: str
    source_chunks_path: str
    embedding_metadata_path: str
    vectors_path: str
    snapshot_id: str | None
    index_path: str | None = None
    row_mapping_path: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DenseIndexMetadata":
        return cls(
            artifact_version=str(payload["artifact_version"]),
            backend_name=str(payload["backend_name"]),
            metric=str(payload["metric"]),
            vector_dimension=int(payload["vector_dimension"]),
            row_count=int(payload["row_count"]),
            embedding_model_name=str(payload["embedding_model_name"]),
            source_chunks_path=str(payload["source_chunks_path"]),
            embedding_metadata_path=str(payload["embedding_metadata_path"]),
            vectors_path=str(payload["vectors_path"]),
            snapshot_id=(str(payload["snapshot_id"]) if payload.get("snapshot_id") else None),
            index_path=(str(payload["index_path"]) if payload.get("index_path") else None),
            row_mapping_path=(
                str(payload["row_mapping_path"]) if payload.get("row_mapping_path") else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChunkRowMapping:
    chunk_ids: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChunkRowMapping":
        return cls(chunk_ids=[str(chunk_id) for chunk_id in payload.get("chunk_ids", [])])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_index_metadata(path: Path, metadata: DenseIndexMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_index_metadata(path: Path) -> DenseIndexMetadata:
    return DenseIndexMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_chunk_row_mapping(path: Path, mapping: ChunkRowMapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(mapping.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_chunk_row_mapping(path: Path) -> ChunkRowMapping:
    return ChunkRowMapping.from_dict(json.loads(path.read_text(encoding="utf-8")))


class DenseRetrievalBackend(Protocol):
    metadata: DenseIndexMetadata

    def search(self, query_vector: Sequence[float], *, top_k: int = 5) -> list[DenseSearchResult]:
        """Return deterministic top-k search results for a single query vector."""

    def save(
        self,
        *,
        index_path: Path,
        metadata_path: Path,
        row_mapping_path: Path,
    ) -> DenseIndexMetadata:
        """Persist backend artifacts to disk."""
