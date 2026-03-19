from __future__ import annotations

import json
from pathlib import Path

import pytest

from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import (
    build_embedding_artifacts,
    read_embedding_metadata,
    read_vector_rows,
)


class DeterministicTestEmbedder:
    model_name = "test-hash-v1"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        rows: list[list[float]] = []
        for text in texts:
            rows.append(
                [
                    float(len(text)),
                    float(sum(ord(character) for character in text) % 997),
                    float(text.count(" ") + 1),
                ]
            )
        return rows


def make_chunk(*, chunk_id: str, text: str, snapshot_id: str = "k8s-9e1e32b") -> ChunkRecord:
    return ChunkRecord(
        snapshot_id=snapshot_id,
        doc_id="content-en-docs-concepts-pods",
        chunk_id=chunk_id,
        section_id=f"section-{chunk_id}",
        section_index=0,
        chunk_index=0,
        doc_title="Pods",
        section_path=["Pods"],
        source_path="content/en/docs/concepts/workloads/pods/pods.md",
        source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
        license="CC BY 4.0",
        attribution="Kubernetes Documentation © The Kubernetes Authors",
        language="en",
        start_offset=0,
        end_offset=len(text),
        token_count=len(text.split()),
        text=text,
    )


def write_chunks(path: Path, chunks: list[ChunkRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )


def test_build_embedding_artifacts_writes_vectors_and_metadata(tmp_path: Path) -> None:
    chunks_path = tmp_path / "data/processed/chunks.jsonl"
    vectors_path = tmp_path / "data/processed/embeddings/chunk_embeddings.f32"
    metadata_path = tmp_path / "data/processed/embeddings/chunk_embeddings.metadata.json"
    chunks = [
        make_chunk(chunk_id="chunk-0001", text="pods run containers"),
        make_chunk(chunk_id="chunk-0002", text="services expose workloads"),
    ]
    write_chunks(chunks_path, chunks)

    metadata = build_embedding_artifacts(
        chunks_path=chunks_path,
        vectors_path=vectors_path,
        metadata_path=metadata_path,
        embedder=DeterministicTestEmbedder(),
        batch_size=1,
    )

    assert vectors_path.exists()
    assert metadata_path.exists()
    assert metadata.row_count == 2
    assert metadata.vector_dimension == 3
    assert metadata.embedding_model_name == "test-hash-v1"
    assert metadata.snapshot_id == "k8s-9e1e32b"
    assert metadata.source_chunks_path == str(chunks_path)

    loaded_metadata = read_embedding_metadata(metadata_path)
    loaded_vectors = read_vector_rows(vectors_path, dimension=loaded_metadata.vector_dimension)
    expected_vectors = DeterministicTestEmbedder().embed_texts([chunk.text for chunk in chunks])

    assert loaded_metadata == metadata
    assert loaded_vectors == expected_vectors


def test_embedding_artifacts_are_deterministic_for_same_input(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    run_a_vectors = tmp_path / "run-a/chunk_embeddings.f32"
    run_a_metadata = tmp_path / "run-a/chunk_embeddings.metadata.json"
    run_b_vectors = tmp_path / "run-b/chunk_embeddings.f32"
    run_b_metadata = tmp_path / "run-b/chunk_embeddings.metadata.json"
    chunks = [
        make_chunk(chunk_id="chunk-0001", text="one two three"),
        make_chunk(chunk_id="chunk-0002", text="four five six seven"),
    ]
    write_chunks(chunks_path, chunks)

    build_embedding_artifacts(
        chunks_path=chunks_path,
        vectors_path=run_a_vectors,
        metadata_path=run_a_metadata,
        embedder=DeterministicTestEmbedder(),
        batch_size=2,
    )
    build_embedding_artifacts(
        chunks_path=chunks_path,
        vectors_path=run_b_vectors,
        metadata_path=run_b_metadata,
        embedder=DeterministicTestEmbedder(),
        batch_size=2,
    )

    metadata_a = read_embedding_metadata(run_a_metadata)
    metadata_b = read_embedding_metadata(run_b_metadata)

    assert metadata_a.row_count == metadata_b.row_count == 2
    assert metadata_a.vector_dimension == metadata_b.vector_dimension == 3
    assert metadata_a.snapshot_id == metadata_b.snapshot_id == "k8s-9e1e32b"
    assert run_a_vectors.read_bytes() == run_b_vectors.read_bytes()
    assert read_vector_rows(run_a_vectors, dimension=3) == read_vector_rows(
        run_b_vectors, dimension=3
    )


def test_build_embedding_artifacts_fails_for_missing_or_empty_chunks(tmp_path: Path) -> None:
    missing_chunks_path = tmp_path / "missing/chunks.jsonl"
    empty_chunks_path = tmp_path / "empty/chunks.jsonl"
    empty_chunks_path.parent.mkdir(parents=True, exist_ok=True)
    empty_chunks_path.write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Chunks artifact not found"):
        build_embedding_artifacts(
            chunks_path=missing_chunks_path,
            vectors_path=tmp_path / "vectors.f32",
            metadata_path=tmp_path / "metadata.json",
            embedder=DeterministicTestEmbedder(),
        )

    with pytest.raises(ValueError, match="Chunks artifact is empty"):
        build_embedding_artifacts(
            chunks_path=empty_chunks_path,
            vectors_path=tmp_path / "vectors.f32",
            metadata_path=tmp_path / "metadata.json",
            embedder=DeterministicTestEmbedder(),
        )
