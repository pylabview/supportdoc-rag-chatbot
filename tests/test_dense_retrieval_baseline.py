from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from supportdoc_rag_chatbot.cli import main
from supportdoc_rag_chatbot.evaluation import read_retrieval_results, read_retrieval_summary
from supportdoc_rag_chatbot.evaluation.dev_qa import DevQAEntry, DevQAMetadata
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


@pytest.fixture
def fake_faiss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "faiss", fake_faiss_module())


@pytest.fixture
def dense_baseline_fixture(tmp_path: Path, fake_faiss) -> dict[str, Path]:
    chunks_path = tmp_path / "data/processed/chunks.jsonl"
    vectors_path = tmp_path / "data/processed/embeddings/chunk_embeddings.f32"
    embedding_metadata_path = tmp_path / "data/processed/embeddings/chunk_embeddings.metadata.json"
    index_path = tmp_path / "data/processed/indexes/faiss/chunk_index.faiss"
    index_metadata_path = tmp_path / "data/processed/indexes/faiss/chunk_index.metadata.json"
    row_mapping_path = tmp_path / "data/processed/indexes/faiss/chunk_index.row_mapping.json"

    dataset_path = tmp_path / "data/evaluation/dev_qa.fixture.v1.jsonl"
    dataset_metadata_path = tmp_path / "data/evaluation/dev_qa.fixture.v1.metadata.json"
    results_output_path = tmp_path / "tmp/eval/dense.results.jsonl"
    summary_output_path = tmp_path / "tmp/eval/dense.summary.json"

    chunks = [
        make_chunk(
            chunk_id="chunk-service",
            doc_id="doc-service",
            section_id="section-service",
            text="Services provide stable networking for backend Pods",
        ),
        make_chunk(
            chunk_id="chunk-probe",
            doc_id="doc-probe",
            section_id="section-probe",
            text="Startup probes protect slow containers from early liveness failures",
        ),
        make_chunk(
            chunk_id="chunk-other",
            doc_id="doc-other",
            section_id="section-other",
            text="Other chunk content that should rank lower",
        ),
    ]
    write_chunks(chunks_path, chunks)

    embedder = MappingTestEmbedder(
        {
            chunks[0].text: [1.0, 0.0, 0.0],
            chunks[1].text: [0.0, 1.0, 0.0],
            chunks[2].text: [0.2, 0.2, 0.0],
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

    entries = [
        DevQAEntry(
            query_id="service-purpose",
            snapshot_id="k8s-9e1e32b",
            question="Why would you use a Kubernetes Service?",
            answerable=True,
            category="definition",
            tags=["services"],
            doc_ids=["doc-service"],
            expected_section_ids=["section-service"],
            expected_chunk_ids=["chunk-service"],
            notes="service evidence",
        ),
        DevQAEntry(
            query_id="startup-probe",
            snapshot_id="k8s-9e1e32b",
            question="How can startup probes protect slow-starting containers?",
            answerable=True,
            category="troubleshooting",
            tags=["probes"],
            doc_ids=["doc-probe"],
            expected_section_ids=["section-probe"],
            expected_chunk_ids=["chunk-probe"],
            notes="probe evidence",
        ),
    ]
    write_dataset(dataset_path, entries)
    write_metadata(
        dataset_metadata_path,
        DevQAMetadata(
            dataset_name="fixture_dense_baseline",
            dataset_version="v1",
            snapshot_id="k8s-9e1e32b",
            source_manifest_path="data/manifests/source_manifest.jsonl",
            artifact_path=str(dataset_path),
            registry_path="data/evaluation/dev_qa.fixture.v1.registry.json",
            row_count=len(entries),
            doc_count=2,
            section_id_count=2,
            chunk_id_count=3,
            default_chunking={"max_tokens": 350, "overlap_tokens": 50},
            notes="fixture metadata",
        ),
    )

    return {
        "dataset_path": dataset_path,
        "dataset_metadata_path": dataset_metadata_path,
        "index_path": index_path,
        "index_metadata_path": index_metadata_path,
        "row_mapping_path": row_mapping_path,
        "results_output_path": results_output_path,
        "summary_output_path": summary_output_path,
    }


def test_run_dense_baseline_cli_writes_retrieval_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dense_baseline_fixture: dict[str, Path],
) -> None:
    from supportdoc_rag_chatbot.evaluation import dense_baseline

    def fake_create_local_embedder(*, model_name, device, batch_size, normalize_embeddings):
        assert model_name == "test-map-v1"
        assert device == "cpu"
        assert batch_size == 32
        assert normalize_embeddings is True
        return QueryTestEmbedder(
            {
                "Why would you use a Kubernetes Service?": [1.0, 0.0, 0.0],
                "How can startup probes protect slow-starting containers?": [0.0, 1.0, 0.0],
            }
        )

    monkeypatch.setattr(dense_baseline, "create_local_embedder", fake_create_local_embedder)

    exit_code = main(
        [
            "run-dense-baseline",
            "--dataset",
            str(dense_baseline_fixture["dataset_path"]),
            "--dataset-metadata",
            str(dense_baseline_fixture["dataset_metadata_path"]),
            "--index",
            str(dense_baseline_fixture["index_path"]),
            "--index-metadata",
            str(dense_baseline_fixture["index_metadata_path"]),
            "--row-mapping",
            str(dense_baseline_fixture["row_mapping_path"]),
            "--top-k",
            "2",
            "--results-output",
            str(dense_baseline_fixture["results_output_path"]),
            "--summary-output",
            str(dense_baseline_fixture["summary_output_path"]),
        ]
    )

    assert exit_code == 0

    results = read_retrieval_results(dense_baseline_fixture["results_output_path"])
    summary = read_retrieval_summary(dense_baseline_fixture["summary_output_path"])

    assert len(results) == 2
    assert [match.chunk_id for match in results[0].matches] == ["chunk-service", "chunk-other"]
    assert [match.chunk_id for match in results[1].matches] == ["chunk-probe", "chunk-other"]
    assert summary.retriever_name == "dense"
    assert summary.top_k == 2
    assert summary.query_count == 2
    assert summary.answerable_query_count == 2
    assert summary.hit_at_k == pytest.approx(1.0)
    assert summary.recall_at_k == pytest.approx(1.0)
    assert summary.mrr == pytest.approx(1.0)
    assert summary.retriever_config["embedding_model_name"] == "test-map-v1"
    assert summary.retriever_config["index_backend"] == "faiss-flat-ip"

    out = capsys.readouterr().out
    assert "Dense retrieval baseline" in out
    assert "embedding_model: test-map-v1" in out
    assert "index_backend: faiss-flat-ip" in out
    assert f"results_output: {dense_baseline_fixture['results_output_path']}" in out
    assert f"summary_output: {dense_baseline_fixture['summary_output_path']}" in out


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


def make_chunk(
    *,
    chunk_id: str,
    doc_id: str,
    section_id: str,
    text: str,
    snapshot_id: str = "k8s-9e1e32b",
) -> ChunkRecord:
    return ChunkRecord(
        snapshot_id=snapshot_id,
        doc_id=doc_id,
        chunk_id=chunk_id,
        section_id=section_id,
        section_index=0,
        chunk_index=0,
        doc_title=doc_id,
        section_path=[section_id],
        source_path=f"{doc_id}.md",
        source_url=f"https://example.test/{doc_id}",
        license="CC BY 4.0",
        attribution="fixture",
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


def write_dataset(path: Path, entries: list[DevQAEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n" for entry in entries),
        encoding="utf-8",
    )


def write_metadata(path: Path, metadata: DevQAMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _numpy():
    import numpy

    return numpy
