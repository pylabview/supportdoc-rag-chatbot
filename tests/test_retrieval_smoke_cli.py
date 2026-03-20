from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from supportdoc_rag_chatbot.cli import main
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import build_embedding_artifacts
from supportdoc_rag_chatbot.retrieval.indexes import build_faiss_index_artifacts


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


class QueryTestEmbedder:
    model_name = "test-query-v1"

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(value) for value in self.mapping[text]] for text in texts]


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
def retrieval_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    install_fake_faiss(monkeypatch)

    chunks_path = tmp_path / "data/processed/chunks.jsonl"
    vectors_path = tmp_path / "data/processed/embeddings/chunk_embeddings.f32"
    embedding_metadata_path = tmp_path / "data/processed/embeddings/chunk_embeddings.metadata.json"
    index_path = tmp_path / "data/processed/indexes/faiss/chunk_index.faiss"
    index_metadata_path = tmp_path / "data/processed/indexes/faiss/chunk_index.metadata.json"
    row_mapping_path = tmp_path / "data/processed/indexes/faiss/chunk_index.row_mapping.json"

    chunks = [
        make_chunk(chunk_id="chunk-alpha", text="alpha pods can run one or more containers"),
        make_chunk(chunk_id="chunk-beta", text="beta pods are related to pod templates"),
        make_chunk(chunk_id="chunk-gamma", text="gamma services expose pods over the network"),
    ]
    write_chunks(chunks_path, chunks)

    embedder = MappingTestEmbedder(
        {
            chunks[0].text: [1.0, 0.0, 0.0],
            chunks[1].text: [0.8, 0.2, 0.0],
            chunks[2].text: [0.0, 1.0, 0.0],
        }
    )
    build_embedding_artifacts(
        chunks_path=chunks_path,
        vectors_path=vectors_path,
        metadata_path=embedding_metadata_path,
        embedder=embedder,
        batch_size=2,
    )
    build_faiss_index_artifacts(
        embedding_metadata_path=embedding_metadata_path,
        index_path=index_path,
        metadata_path=index_metadata_path,
        row_mapping_path=row_mapping_path,
    )

    return {
        "chunks_path": chunks_path,
        "index_path": index_path,
        "index_metadata_path": index_metadata_path,
        "row_mapping_path": row_mapping_path,
    }


def test_smoke_dense_retrieval_cli_prints_ranked_matches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    retrieval_fixture: dict[str, Path],
) -> None:
    from supportdoc_rag_chatbot.retrieval import smoke

    captured: dict[str, object] = {}

    def fake_create_local_embedder(*, model_name, device, batch_size, normalize_embeddings):
        captured["model_name"] = model_name
        captured["device"] = device
        captured["batch_size"] = batch_size
        captured["normalize_embeddings"] = normalize_embeddings
        return QueryTestEmbedder({"alpha pods": [1.0, 0.0, 0.0]})

    monkeypatch.setattr(smoke, "create_local_embedder", fake_create_local_embedder)

    exit_code = main(
        [
            "smoke-dense-retrieval",
            "--query",
            "alpha pods",
            "--top-k",
            "2",
            "--index",
            str(retrieval_fixture["index_path"]),
            "--index-metadata",
            str(retrieval_fixture["index_metadata_path"]),
            "--row-mapping",
            str(retrieval_fixture["row_mapping_path"]),
            "--chunks",
            str(retrieval_fixture["chunks_path"]),
            "--preview-chars",
            "24",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "model_name": "test-map-v1",
        "device": "cpu",
        "batch_size": 32,
        "normalize_embeddings": True,
    }

    out = capsys.readouterr().out
    assert "Dense retrieval smoke test" in out
    assert 'query: "alpha pods"' in out
    assert "model: test-map-v1" in out
    assert "[1] score=" in out
    assert "chunk_id=chunk-alpha" in out
    assert "chunk_id=chunk-beta" in out
    assert out.index("chunk_id=chunk-alpha") < out.index("chunk_id=chunk-beta")
    assert "section_path: Pods" in out
    assert "source_url: https://kubernetes.io/docs/concepts/workloads/pods/" in out
    assert "preview: alpha pods can run one…" in out


def test_smoke_dense_retrieval_cli_fails_when_index_metadata_is_missing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    exit_code = main(
        [
            "smoke-dense-retrieval",
            "--query",
            "alpha pods",
            "--index-metadata",
            str(tmp_path / "missing/chunk_index.metadata.json"),
        ]
    )

    assert exit_code == 2
    expected_error = tmp_path / "missing/chunk_index.metadata.json"
    assert f"Error: Index metadata artifact not found: {expected_error}" in capsys.readouterr().err


def _numpy():
    import numpy

    return numpy
