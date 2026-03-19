from __future__ import annotations

import json
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

ARTIFACT_VERSION = "v1"
VECTOR_DTYPE = "float32"
_FLOAT32_SIZE_BYTES = 4


@dataclass(slots=True)
class EmbeddingMetadata:
    artifact_version: str
    source_chunks_path: str
    embedding_model_name: str
    vector_dimension: int
    row_count: int
    snapshot_id: str | None
    dtype: str = VECTOR_DTYPE
    vectors_path: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EmbeddingMetadata":
        return cls(
            artifact_version=str(payload["artifact_version"]),
            source_chunks_path=str(payload["source_chunks_path"]),
            embedding_model_name=str(payload["embedding_model_name"]),
            vector_dimension=int(payload["vector_dimension"]),
            row_count=int(payload["row_count"]),
            snapshot_id=(str(payload["snapshot_id"]) if payload.get("snapshot_id") else None),
            dtype=str(payload.get("dtype", VECTOR_DTYPE)),
            vectors_path=(str(payload["vectors_path"]) if payload.get("vectors_path") else None),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_embedding_metadata(path: Path, metadata: EmbeddingMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_embedding_metadata(path: Path) -> EmbeddingMetadata:
    return EmbeddingMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_vector_rows(path: Path, rows: Iterable[Sequence[float]]) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)

    dimension: int | None = None
    row_count = 0

    with path.open("wb") as handle:
        for row_index, row in enumerate(rows):
            row_values = [float(value) for value in row]
            if dimension is None:
                dimension = len(row_values)
                if dimension <= 0:
                    raise ValueError("Embedding vectors must have at least one dimension")
            elif len(row_values) != dimension:
                raise ValueError(
                    f"Inconsistent embedding dimension at row {row_index}: "
                    f"expected {dimension}, got {len(row_values)}"
                )

            array("f", row_values).tofile(handle)
            row_count += 1

    if row_count == 0 or dimension is None:
        raise ValueError("No embedding vectors were produced")

    return row_count, dimension


def read_vector_rows(path: Path, *, dimension: int) -> list[list[float]]:
    if dimension <= 0:
        raise ValueError("dimension must be > 0")

    if not path.exists():
        raise FileNotFoundError(f"Vector artifact not found: {path}")

    total_bytes = path.stat().st_size
    if total_bytes % _FLOAT32_SIZE_BYTES != 0:
        raise ValueError(f"Vector artifact is not aligned to float32 values: {path}")

    total_values = total_bytes // _FLOAT32_SIZE_BYTES
    if total_values % dimension != 0:
        raise ValueError(
            f"Vector artifact size is not divisible by the embedding dimension "
            f"({dimension}) for {path}"
        )

    values = array("f")
    with path.open("rb") as handle:
        values.fromfile(handle, total_values)

    row_count = total_values // dimension
    return [
        list(values[offset : offset + dimension]) for offset in range(0, len(values), dimension)
    ]
