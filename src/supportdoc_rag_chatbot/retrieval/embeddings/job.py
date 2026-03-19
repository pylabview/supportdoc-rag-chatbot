from __future__ import annotations

from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from supportdoc_rag_chatbot.ingestion.jsonl import read_jsonl
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord

from .artifacts import (
    ARTIFACT_VERSION,
    EmbeddingMetadata,
    write_embedding_metadata,
    write_vector_rows,
)
from .models import DenseEmbedder

DEFAULT_CHUNKS_PATH = Path("data/processed/chunks.jsonl")
DEFAULT_EMBEDDINGS_DIR = Path("data/processed/embeddings")
DEFAULT_VECTORS_PATH = DEFAULT_EMBEDDINGS_DIR / "chunk_embeddings.f32"
DEFAULT_METADATA_PATH = DEFAULT_EMBEDDINGS_DIR / "chunk_embeddings.metadata.json"
DEFAULT_BATCH_SIZE = 32


def load_chunk_records(path: Path) -> list[ChunkRecord]:
    if not path.exists():
        raise FileNotFoundError(f"Chunks artifact not found: {path}")

    chunks = [ChunkRecord.from_dict(payload) for payload in read_jsonl(path)]
    if not chunks:
        raise ValueError(f"Chunks artifact is empty: {path}")

    return chunks


def _batched(items: Sequence[ChunkRecord], batch_size: int) -> Iterator[list[ChunkRecord]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    iterator = iter(items)
    while batch := list(islice(iterator, batch_size)):
        yield batch


def _resolve_snapshot_id(chunks: Iterable[ChunkRecord]) -> str | None:
    snapshot_ids = {chunk.snapshot_id for chunk in chunks if chunk.snapshot_id}
    if len(snapshot_ids) == 1:
        return next(iter(snapshot_ids))
    return None


def build_embedding_artifacts(
    *,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    vectors_path: Path = DEFAULT_VECTORS_PATH,
    metadata_path: Path = DEFAULT_METADATA_PATH,
    embedder: DenseEmbedder,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> EmbeddingMetadata:
    chunks = load_chunk_records(chunks_path)
    expected_rows = len(chunks)

    def iter_embedding_rows() -> Iterator[list[float]]:
        produced_rows = 0
        for batch in _batched(chunks, batch_size=batch_size):
            vectors = embedder.embed_texts([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise ValueError(
                    f"Embedding backend returned {len(vectors)} rows for a batch of {len(batch)} chunks"
                )

            for vector in vectors:
                produced_rows += 1
                yield vector

        if produced_rows != expected_rows:
            raise ValueError(
                f"Embedding backend returned {produced_rows} rows for {expected_rows} chunks"
            )

    row_count, vector_dimension = write_vector_rows(vectors_path, iter_embedding_rows())

    metadata = EmbeddingMetadata(
        artifact_version=ARTIFACT_VERSION,
        source_chunks_path=str(chunks_path),
        embedding_model_name=embedder.model_name,
        vector_dimension=vector_dimension,
        row_count=row_count,
        snapshot_id=_resolve_snapshot_id(chunks),
        vectors_path=str(vectors_path),
    )
    write_embedding_metadata(metadata_path, metadata)
    return metadata
