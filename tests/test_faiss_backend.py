from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import build_embedding_artifacts
from supportdoc_rag_chatbot.retrieval.indexes import (
    build_faiss_index_artifacts,
    load_faiss_index_backend,
    read_index_metadata,
)


class MappingTestEmbedder:
    model_name = "test-map-v1"

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(value) for value in self.mapping[text]] for text in texts]


class FakeFaissIndexFlatIP:
    def __init__(self, dimension: int) -> None:
        self.d = int(dimension)
        self.ntotal = 0
        self._vectors = _numpy().empty((0, self.d), dtype=_numpy().float32)

    def add(self, vectors) -> None:
        vectors_array = _numpy().asarray(vectors, dtype=_numpy().float32)
        if vectors_array.ndim != 2 or vectors_array.shape[1] != self.d:
            raise ValueError("FakeFaissIndexFlatIP.add received vectors with the wrong shape")
        self._vectors = _numpy().vstack([self._vectors, vectors_array])
        self.ntotal = int(self._vectors.shape[0])

    def search(self, queries, top_k: int):
        queries_array = _numpy().asarray(queries, dtype=_numpy().float32)
        scores = queries_array @ self._vectors.T
        ranked_indexes = _numpy().argsort(-scores, axis=1, kind="stable")[:, :top_k]
        ranked_scores = _numpy().take_along_axis(scores, ranked_indexes, axis=1)
        return ranked_scores.astype(_numpy().float32), ranked_indexes.astype(_numpy().int64)


def fake_faiss_module() -> SimpleNamespace:
    def normalize_l2(matrix) -> None:
        array = _numpy().asarray(matrix, dtype=_numpy().float32)
        norms = _numpy().linalg.norm(array, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        array /= norms

    def write_index(index: FakeFaissIndexFlatIP, path: str) -> None:
        payload = {"d": index.d, "vectors": index._vectors}
        with Path(path).open("wb") as handle:
            pickle.dump(payload, handle)

    def read_index(path: str) -> FakeFaissIndexFlatIP:
        with Path(path).open("rb") as handle:
            payload = pickle.load(handle)
        index = FakeFaissIndexFlatIP(payload["d"])
        index.add(payload["vectors"])
        return index

    return SimpleNamespace(
        IndexFlatIP=FakeFaissIndexFlatIP,
        normalize_L2=normalize_l2,
        write_index=write_index,
        read_index=read_index,
    )


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


def install_fake_faiss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "faiss", fake_faiss_module())


@pytest.fixture
def embedded_chunks(tmp_path: Path) -> dict[str, Path]:
    chunks_path = tmp_path / "data/processed/chunks.jsonl"
    vectors_path = tmp_path / "data/processed/embeddings/chunk_embeddings.f32"
    embedding_metadata_path = tmp_path / "data/processed/embeddings/chunk_embeddings.metadata.json"

    chunks = [
        make_chunk(chunk_id="chunk-alpha", text="alpha"),
        make_chunk(chunk_id="chunk-beta", text="beta"),
        make_chunk(chunk_id="chunk-gamma", text="gamma"),
    ]
    write_chunks(chunks_path, chunks)

    embedder = MappingTestEmbedder(
        {
            "alpha": [1.0, 0.0, 0.0],
            "beta": [0.8, 0.2, 0.0],
            "gamma": [0.0, 1.0, 0.0],
        }
    )
    build_embedding_artifacts(
        chunks_path=chunks_path,
        vectors_path=vectors_path,
        metadata_path=embedding_metadata_path,
        embedder=embedder,
        batch_size=2,
    )

    return {
        "chunks_path": chunks_path,
        "vectors_path": vectors_path,
        "embedding_metadata_path": embedding_metadata_path,
    }


def test_build_load_and_search_faiss_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    embedded_chunks: dict[str, Path],
) -> None:
    install_fake_faiss(monkeypatch)

    index_path = tmp_path / "data/processed/indexes/faiss/chunk_index.faiss"
    index_metadata_path = tmp_path / "data/processed/indexes/faiss/chunk_index.metadata.json"
    row_mapping_path = tmp_path / "data/processed/indexes/faiss/chunk_index.row_mapping.json"

    metadata = build_faiss_index_artifacts(
        embedding_metadata_path=embedded_chunks["embedding_metadata_path"],
        index_path=index_path,
        metadata_path=index_metadata_path,
        row_mapping_path=row_mapping_path,
    )

    assert index_path.exists()
    assert index_metadata_path.exists()
    assert row_mapping_path.exists()
    assert metadata.row_count == 3
    assert metadata.vector_dimension == 3
    assert metadata.embedding_model_name == "test-map-v1"
    assert metadata.index_path == str(index_path)
    assert metadata.row_mapping_path == str(row_mapping_path)

    loaded_metadata = read_index_metadata(index_metadata_path)
    assert loaded_metadata == metadata

    backend = load_faiss_index_backend(
        index_path=index_path,
        metadata_path=index_metadata_path,
    )
    results = backend.search([1.0, 0.0, 0.0], top_k=3)

    assert [result.chunk_id for result in results] == [
        "chunk-alpha",
        "chunk-beta",
        "chunk-gamma",
    ]
    assert [result.rank for result in results] == [1, 2, 3]
    assert [result.row_index for result in results] == [0, 1, 2]
    assert all(
        result.source_chunks_path == str(embedded_chunks["chunks_path"]) for result in results
    )
    assert results[0].score > results[1].score > results[2].score


def test_build_faiss_index_artifacts_fail_on_row_count_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    embedded_chunks: dict[str, Path],
) -> None:
    install_fake_faiss(monkeypatch)

    embedded_chunks["chunks_path"].write_text(
        embedded_chunks["chunks_path"].read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="Embedding metadata row count does not match source chunks"
    ):
        build_faiss_index_artifacts(
            embedding_metadata_path=embedded_chunks["embedding_metadata_path"],
            index_path=tmp_path / "chunk_index.faiss",
            metadata_path=tmp_path / "chunk_index.metadata.json",
            row_mapping_path=tmp_path / "chunk_index.row_mapping.json",
        )


@pytest.mark.skipif(importlib.util.find_spec("faiss") is None, reason="faiss extra not installed")
def test_real_faiss_search_matches_expected_order(
    tmp_path: Path,
    embedded_chunks: dict[str, Path],
) -> None:
    index_path = tmp_path / "real/chunk_index.faiss"
    index_metadata_path = tmp_path / "real/chunk_index.metadata.json"
    row_mapping_path = tmp_path / "real/chunk_index.row_mapping.json"

    build_faiss_index_artifacts(
        embedding_metadata_path=embedded_chunks["embedding_metadata_path"],
        index_path=index_path,
        metadata_path=index_metadata_path,
        row_mapping_path=row_mapping_path,
    )
    backend = load_faiss_index_backend(index_path=index_path, metadata_path=index_metadata_path)
    results = backend.search([1.0, 0.0, 0.0], top_k=2)

    assert [result.chunk_id for result in results] == ["chunk-alpha", "chunk-beta"]
    assert [result.rank for result in results] == [1, 2]


def _numpy():
    import numpy

    return numpy
