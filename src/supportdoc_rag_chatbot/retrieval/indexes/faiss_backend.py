from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from supportdoc_rag_chatbot.retrieval.embeddings import (
    DEFAULT_METADATA_PATH as DEFAULT_EMBEDDING_METADATA_PATH,
    load_chunk_records,
    read_embedding_metadata,
)

from .base import (
    INDEX_ARTIFACT_VERSION,
    ChunkRowMapping,
    DenseIndexMetadata,
    DenseSearchResult,
    read_chunk_row_mapping,
    read_index_metadata,
    write_chunk_row_mapping,
    write_index_metadata,
)

DEFAULT_FAISS_INDEX_DIR = Path("data/processed/indexes/faiss")
DEFAULT_FAISS_INDEX_PATH = DEFAULT_FAISS_INDEX_DIR / "chunk_index.faiss"
DEFAULT_FAISS_METADATA_PATH = DEFAULT_FAISS_INDEX_DIR / "chunk_index.metadata.json"
DEFAULT_FAISS_ROW_MAPPING_PATH = DEFAULT_FAISS_INDEX_DIR / "chunk_index.row_mapping.json"
DEFAULT_FAISS_BACKEND_NAME = "faiss-flat-ip"
DEFAULT_FAISS_METRIC = "cosine-similarity"


@dataclass(slots=True)
class FaissDenseIndexBackend:
    index: Any
    metadata: DenseIndexMetadata
    chunk_ids: list[str]

    def search(self, query_vector: Sequence[float], *, top_k: int = 5) -> list[DenseSearchResult]:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")

        if not self.chunk_ids:
            return []

        vector_dimension = self.metadata.vector_dimension
        query = _to_query_matrix(query_vector, dimension=vector_dimension)
        faiss = _load_faiss_module()
        faiss.normalize_L2(query)

        search_k = min(int(top_k), len(self.chunk_ids))
        scores, row_indexes = self.index.search(query, search_k)
        pairs = zip(scores[0].tolist(), row_indexes[0].tolist(), strict=True)
        sorted_pairs = sorted(
            ((float(score), int(row_index)) for score, row_index in pairs if row_index >= 0),
            key=lambda item: (-item[0], item[1]),
        )

        results: list[DenseSearchResult] = []
        for rank, (score, row_index) in enumerate(sorted_pairs, start=1):
            results.append(
                DenseSearchResult(
                    chunk_id=self.chunk_ids[row_index],
                    score=score,
                    rank=rank,
                    row_index=row_index,
                    source_chunks_path=self.metadata.source_chunks_path,
                )
            )
        return results

    def save(
        self,
        *,
        index_path: Path,
        metadata_path: Path,
        row_mapping_path: Path,
    ) -> DenseIndexMetadata:
        faiss = _load_faiss_module()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        row_mapping_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(index_path))
        write_chunk_row_mapping(row_mapping_path, ChunkRowMapping(chunk_ids=list(self.chunk_ids)))

        persisted_metadata = DenseIndexMetadata(
            artifact_version=self.metadata.artifact_version,
            backend_name=self.metadata.backend_name,
            metric=self.metadata.metric,
            vector_dimension=self.metadata.vector_dimension,
            row_count=self.metadata.row_count,
            embedding_model_name=self.metadata.embedding_model_name,
            source_chunks_path=self.metadata.source_chunks_path,
            embedding_metadata_path=self.metadata.embedding_metadata_path,
            vectors_path=self.metadata.vectors_path,
            snapshot_id=self.metadata.snapshot_id,
            index_path=str(index_path),
            row_mapping_path=str(row_mapping_path),
        )
        write_index_metadata(metadata_path, persisted_metadata)
        self.metadata = persisted_metadata
        return persisted_metadata


def build_faiss_index_backend(
    *,
    embedding_metadata_path: Path = DEFAULT_EMBEDDING_METADATA_PATH,
) -> FaissDenseIndexBackend:
    embedding_metadata = read_embedding_metadata(embedding_metadata_path)
    vectors_path = _resolve_vectors_path(
        embedding_metadata_path=embedding_metadata_path,
        raw_path=embedding_metadata.vectors_path,
    )
    chunks_path = _required_artifact_path(
        embedding_metadata.source_chunks_path,
        label="source_chunks_path",
        source_path=embedding_metadata_path,
    )

    vectors = _read_vector_matrix(vectors_path, dimension=embedding_metadata.vector_dimension)
    chunks = load_chunk_records(chunks_path)

    if len(chunks) != embedding_metadata.row_count:
        raise ValueError(
            "Embedding metadata row count does not match source chunks: "
            f"expected {embedding_metadata.row_count}, got {len(chunks)}"
        )
    if vectors.shape[0] != embedding_metadata.row_count:
        raise ValueError(
            "Embedding metadata row count does not match vector artifact: "
            f"expected {embedding_metadata.row_count}, got {vectors.shape[0]}"
        )

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    faiss = _load_faiss_module()
    index = faiss.IndexFlatIP(embedding_metadata.vector_dimension)
    normalized_vectors = vectors.copy()
    faiss.normalize_L2(normalized_vectors)
    index.add(normalized_vectors)

    metadata = DenseIndexMetadata(
        artifact_version=INDEX_ARTIFACT_VERSION,
        backend_name=DEFAULT_FAISS_BACKEND_NAME,
        metric=DEFAULT_FAISS_METRIC,
        vector_dimension=embedding_metadata.vector_dimension,
        row_count=embedding_metadata.row_count,
        embedding_model_name=embedding_metadata.embedding_model_name,
        source_chunks_path=str(chunks_path),
        embedding_metadata_path=str(embedding_metadata_path),
        vectors_path=str(vectors_path),
        snapshot_id=embedding_metadata.snapshot_id,
    )
    return FaissDenseIndexBackend(index=index, metadata=metadata, chunk_ids=chunk_ids)


def build_faiss_index_artifacts(
    *,
    embedding_metadata_path: Path = DEFAULT_EMBEDDING_METADATA_PATH,
    index_path: Path = DEFAULT_FAISS_INDEX_PATH,
    metadata_path: Path = DEFAULT_FAISS_METADATA_PATH,
    row_mapping_path: Path = DEFAULT_FAISS_ROW_MAPPING_PATH,
) -> DenseIndexMetadata:
    backend = build_faiss_index_backend(embedding_metadata_path=embedding_metadata_path)
    return backend.save(
        index_path=index_path,
        metadata_path=metadata_path,
        row_mapping_path=row_mapping_path,
    )


def load_faiss_index_backend(
    *,
    index_path: Path = DEFAULT_FAISS_INDEX_PATH,
    metadata_path: Path = DEFAULT_FAISS_METADATA_PATH,
    row_mapping_path: Path | None = None,
) -> FaissDenseIndexBackend:
    faiss = _load_faiss_module()
    metadata = read_index_metadata(metadata_path)
    resolved_row_mapping_path = row_mapping_path or _required_artifact_path(
        metadata.row_mapping_path,
        label="row_mapping_path",
        source_path=metadata_path,
    )
    row_mapping = read_chunk_row_mapping(resolved_row_mapping_path)

    if metadata.backend_name != DEFAULT_FAISS_BACKEND_NAME:
        raise ValueError(
            f"Index metadata backend_name must be {DEFAULT_FAISS_BACKEND_NAME!r}, "
            f"got {metadata.backend_name!r}"
        )
    if len(row_mapping.chunk_ids) != metadata.row_count:
        raise ValueError(
            "Index row mapping count does not match metadata row count: "
            f"expected {metadata.row_count}, got {len(row_mapping.chunk_ids)}"
        )

    index = faiss.read_index(str(index_path))
    if getattr(index, "d", None) != metadata.vector_dimension:
        raise ValueError(
            "Loaded FAISS index dimension does not match metadata vector dimension: "
            f"expected {metadata.vector_dimension}, got {getattr(index, 'd', None)}"
        )
    if getattr(index, "ntotal", None) != metadata.row_count:
        raise ValueError(
            "Loaded FAISS index row count does not match metadata row count: "
            f"expected {metadata.row_count}, got {getattr(index, 'ntotal', None)}"
        )

    return FaissDenseIndexBackend(index=index, metadata=metadata, chunk_ids=row_mapping.chunk_ids)


def _resolve_vectors_path(*, embedding_metadata_path: Path, raw_path: str | None) -> Path:
    if not raw_path:
        raise ValueError(f"Missing vectors_path in artifact metadata: {embedding_metadata_path}")

    resolved = Path(raw_path)
    if resolved.is_absolute():
        return resolved

    metadata_relative = embedding_metadata_path.parent / resolved

    # New embedding metadata writes vectors_path relative to the metadata file.
    # Keep a small fallback for older repo-root-relative metadata during transition.
    if metadata_relative.exists() or not resolved.exists():
        return metadata_relative
    return resolved


def _required_artifact_path(raw_path: str | None, *, label: str, source_path: Path) -> Path:
    if not raw_path:
        raise ValueError(f"Missing {label} in artifact metadata: {source_path}")
    return Path(raw_path)


def _read_vector_matrix(path: Path, *, dimension: int) -> Any:
    if dimension <= 0:
        raise ValueError("dimension must be > 0")
    if not path.exists():
        raise FileNotFoundError(f"Vector artifact not found: {path}")

    numpy = _load_numpy_module()
    values = numpy.fromfile(path, dtype=numpy.float32)
    if values.size == 0:
        raise ValueError(f"Vector artifact is empty: {path}")
    if values.size % dimension != 0:
        raise ValueError(
            f"Vector artifact size is not divisible by the embedding dimension ({dimension}) for {path}"
        )
    return values.reshape((-1, dimension))


def _to_query_matrix(query_vector: Sequence[float], *, dimension: int) -> Any:
    numpy = _load_numpy_module()
    query = numpy.asarray(list(query_vector), dtype=numpy.float32)
    if query.ndim != 1:
        raise ValueError("query_vector must be one-dimensional")
    if query.size != dimension:
        raise ValueError(f"query_vector dimension mismatch: expected {dimension}, got {query.size}")
    return query.reshape((1, dimension))


def _load_faiss_module() -> Any:
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover - depends on optional local extras
        raise RuntimeError(
            "FAISS dependencies are not installed. "
            "Run `uv sync --locked --extra dev-tools --extra faiss`."
        ) from exc
    return faiss


def _load_numpy_module() -> Any:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - numpy should come with faiss-cpu
        raise RuntimeError(
            "NumPy is required for local FAISS indexing. "
            "Run `uv sync --locked --extra dev-tools --extra faiss`."
        ) from exc
    return numpy
