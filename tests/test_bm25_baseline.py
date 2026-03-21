from __future__ import annotations

import json
from pathlib import Path

import pytest

from supportdoc_rag_chatbot.cli import main
from supportdoc_rag_chatbot.evaluation import read_retrieval_results, read_retrieval_summary
from supportdoc_rag_chatbot.evaluation.dev_qa import DevQAEntry, DevQAMetadata, EvidenceRegistry
from supportdoc_rag_chatbot.evaluation.retrievers import BM25ChunkEvaluationRetriever
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord


@pytest.fixture
def bm25_baseline_fixture(tmp_path: Path) -> dict[str, Path]:
    chunks_path = tmp_path / "data/processed/chunks.jsonl"
    dataset_path = tmp_path / "data/evaluation/dev_qa.fixture.v1.jsonl"
    dataset_metadata_path = tmp_path / "data/evaluation/dev_qa.fixture.v1.metadata.json"
    registry_path = tmp_path / "data/evaluation/dev_qa.fixture.v1.registry.json"
    results_output_path = tmp_path / "tmp/eval/bm25.results.jsonl"
    summary_output_path = tmp_path / "tmp/eval/bm25.summary.json"

    chunks = [
        make_chunk(
            chunk_id="chunk-service",
            doc_id="doc-service",
            section_id="section-service",
            text="A Kubernetes Service provides stable networking in front of Pods.",
        ),
        make_chunk(
            chunk_id="chunk-probe",
            doc_id="doc-probe",
            section_id="section-probe",
            text="Startup probes protect slow-starting containers from early restarts.",
        ),
        make_chunk(
            chunk_id="chunk-noise",
            doc_id="doc-noise",
            section_id="section-noise",
            text="This chunk discusses unrelated scheduling details.",
        ),
    ]
    write_chunks(chunks_path, chunks)

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
            dataset_name="fixture_bm25_baseline",
            dataset_version="v1",
            snapshot_id="k8s-9e1e32b",
            source_manifest_path="data/manifests/source_manifest.jsonl",
            artifact_path=str(dataset_path),
            registry_path=str(registry_path),
            row_count=len(entries),
            doc_count=3,
            section_id_count=3,
            chunk_id_count=3,
            default_chunking={"max_tokens": 350, "overlap_tokens": 50},
            notes="fixture metadata",
        ),
    )
    write_registry(
        registry_path,
        EvidenceRegistry(
            snapshot_id="k8s-9e1e32b",
            source_manifest_path="data/manifests/source_manifest.jsonl",
            doc_ids=["doc-noise", "doc-probe", "doc-service"],
            section_ids=["section-noise", "section-probe", "section-service"],
            chunk_ids=["chunk-noise", "chunk-probe", "chunk-service"],
            default_chunking={"max_tokens": 350, "overlap_tokens": 50},
        ),
    )

    return {
        "chunks_path": chunks_path,
        "dataset_path": dataset_path,
        "dataset_metadata_path": dataset_metadata_path,
        "registry_path": registry_path,
        "results_output_path": results_output_path,
        "summary_output_path": summary_output_path,
    }


def test_run_bm25_baseline_cli_writes_retrieval_artifacts(
    capsys: pytest.CaptureFixture[str],
    bm25_baseline_fixture: dict[str, Path],
) -> None:
    exit_code = main(
        [
            "run-bm25-baseline",
            "--chunks",
            str(bm25_baseline_fixture["chunks_path"]),
            "--dataset",
            str(bm25_baseline_fixture["dataset_path"]),
            "--dataset-metadata",
            str(bm25_baseline_fixture["dataset_metadata_path"]),
            "--registry",
            str(bm25_baseline_fixture["registry_path"]),
            "--top-k",
            "2",
            "--results-output",
            str(bm25_baseline_fixture["results_output_path"]),
            "--summary-output",
            str(bm25_baseline_fixture["summary_output_path"]),
        ]
    )

    assert exit_code == 0

    results = read_retrieval_results(bm25_baseline_fixture["results_output_path"])
    summary = read_retrieval_summary(bm25_baseline_fixture["summary_output_path"])

    assert len(results) == 2
    assert [match.chunk_id for match in results[0].matches] == ["chunk-service"]
    assert [match.chunk_id for match in results[1].matches] == ["chunk-probe"]
    assert summary.retriever_name == "bm25"
    assert summary.top_k == 2
    assert summary.query_count == 2
    assert summary.answerable_query_count == 2
    assert summary.hit_at_k == pytest.approx(1.0)
    assert summary.recall_at_k == pytest.approx(1.0)
    assert summary.mrr == pytest.approx(1.0)
    assert summary.retriever_config["k1"] == pytest.approx(1.5)
    assert summary.retriever_config["b"] == pytest.approx(0.75)
    assert "tokenization" in summary.retriever_config

    out = capsys.readouterr().out
    assert "BM25 retrieval baseline" in out
    assert "k1: 1.5" in out
    assert "b: 0.75" in out
    assert f"results_output: {bm25_baseline_fixture['results_output_path']}" in out
    assert f"summary_output: {bm25_baseline_fixture['summary_output_path']}" in out


def test_bm25_retriever_rejects_empty_chunks_fixture(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text("", encoding="utf-8")
    retriever = BM25ChunkEvaluationRetriever(chunks_path=chunks_path)
    entry = DevQAEntry(
        query_id="q1",
        snapshot_id="k8s-9e1e32b",
        question="What is a Service?",
        answerable=True,
        category="definition",
        tags=[],
        doc_ids=[],
        expected_section_ids=[],
        expected_chunk_ids=[],
        notes="",
    )

    with pytest.raises(ValueError, match="Chunks artifact is empty"):
        retriever.retrieve(entry, top_k=5)


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


def write_registry(path: Path, registry: EvidenceRegistry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
