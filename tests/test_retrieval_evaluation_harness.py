from __future__ import annotations

import json
from pathlib import Path

from supportdoc_rag_chatbot.cli import main
from supportdoc_rag_chatbot.evaluation import (
    DEFAULT_EVAL_TOP_K,
    BM25ChunkEvaluationRetriever,
    DevQAEntry,
    DevQAMetadata,
    EvidenceRegistry,
    HybridRRFEvaluationRetriever,
    RetrievalHit,
    StaticEvaluationRetriever,
    build_retrieval_run_id,
    create_dev_qa_fixture_retriever,
    default_retrieval_run_paths,
    evaluate_retriever,
    load_query_results,
    load_retrieval_run_summary,
    write_query_results,
    write_retrieval_run_summary,
)


def _build_fixture_entries() -> list[DevQAEntry]:
    return [
        DevQAEntry(
            query_id="q1",
            snapshot_id="snap-1",
            question="How do Services help unstable Pods?",
            answerable=True,
            category="definition",
            tags=["services"],
            doc_ids=["doc-a"],
            expected_section_ids=["sec-a"],
            expected_chunk_ids=["chunk-a", "chunk-b"],
            notes="",
        ),
        DevQAEntry(
            query_id="q2",
            snapshot_id="snap-1",
            question="What happens when a readiness probe fails?",
            answerable=True,
            category="troubleshooting",
            tags=["probes"],
            doc_ids=["doc-b"],
            expected_section_ids=["sec-b"],
            expected_chunk_ids=["chunk-c"],
            notes="",
        ),
        DevQAEntry(
            query_id="q3",
            snapshot_id="snap-1",
            question="How do you configure a UDP readiness probe?",
            answerable=False,
            category="insufficient-evidence",
            tags=["probes", "udp"],
            doc_ids=[],
            expected_section_ids=[],
            expected_chunk_ids=[],
            notes="",
        ),
    ]


def _build_fixture_metadata() -> DevQAMetadata:
    return DevQAMetadata(
        dataset_name="tiny_dev_qa",
        dataset_version="v1",
        snapshot_id="snap-1",
        source_manifest_path="data/manifests/source_manifest.jsonl",
        artifact_path="data/evaluation/tiny_dev_qa.jsonl",
        registry_path="data/evaluation/tiny_dev_qa.registry.json",
        row_count=3,
        doc_count=2,
        section_id_count=2,
        chunk_id_count=4,
        default_chunking={"max_tokens": 350, "overlap_tokens": 50},
        notes="",
    )


def _build_fixture_registry() -> EvidenceRegistry:
    return EvidenceRegistry(
        snapshot_id="snap-1",
        source_manifest_path="data/manifests/source_manifest.jsonl",
        doc_ids=["doc-a", "doc-b"],
        section_ids=["sec-a", "sec-b"],
        chunk_ids=["chunk-a", "chunk-b", "chunk-c", "chunk-noise"],
        default_chunking={"max_tokens": 350, "overlap_tokens": 50},
    )


def _write_dev_qa_fixture_files(
    tmp_path: Path,
    *,
    entries: list[DevQAEntry],
    metadata: DevQAMetadata,
    registry: EvidenceRegistry,
) -> tuple[Path, Path, Path]:
    dataset_path = tmp_path / "dev_qa.jsonl"
    metadata_path = tmp_path / "dev_qa.metadata.json"
    registry_path = tmp_path / "dev_qa.registry.json"

    dataset_path.write_text(
        "".join(json.dumps(entry.to_dict()) + "\n" for entry in entries),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata.to_dict(), indent=2) + "\n", encoding="utf-8")
    registry_path.write_text(json.dumps(registry.to_dict(), indent=2) + "\n", encoding="utf-8")
    return dataset_path, metadata_path, registry_path


def test_evaluate_retriever_computes_metrics_and_writes_artifacts(tmp_path: Path) -> None:
    entries = _build_fixture_entries()
    metadata = _build_fixture_metadata()
    registry = _build_fixture_registry()

    retriever = StaticEvaluationRetriever(
        name="fixture-dense",
        retriever_type="dense",
        hits_by_query_id={
            "q1": [
                RetrievalHit(
                    chunk_id="chunk-b", score=0.90, rank=1, doc_id="doc-a", section_id="sec-a"
                ),
                RetrievalHit(
                    chunk_id="chunk-noise", score=0.10, rank=2, doc_id="doc-b", section_id="sec-b"
                ),
            ],
            "q2": [
                RetrievalHit(
                    chunk_id="chunk-noise", score=0.80, rank=1, doc_id="doc-b", section_id="sec-b"
                ),
                RetrievalHit(
                    chunk_id="chunk-c", score=0.70, rank=2, doc_id="doc-b", section_id="sec-b"
                ),
            ],
            "q3": [],
        },
        config={"fixture": True},
    )

    ticks = iter([0, 1_000_000, 1_000_000, 3_000_000, 3_000_000, 4_000_000])
    results, summary = evaluate_retriever(
        retriever=retriever,
        entries=entries,
        metadata=metadata,
        registry=registry,
        top_k=2,
        clock_ns=lambda: next(ticks),
    )

    assert len(results) == 3
    assert summary.total_query_count == 3
    assert summary.answerable_query_count == 2
    assert summary.unanswerable_query_count == 1
    assert summary.hit_at_k == 1.0
    assert summary.recall_at_k == 0.75
    assert summary.mrr == 0.75
    assert summary.average_latency_ms == 1.333333
    assert summary.p50_latency_ms == 1.0
    assert summary.p95_latency_ms == 2.0
    assert summary.max_latency_ms == 2.0

    results_path = tmp_path / "results.jsonl"
    summary_path = tmp_path / "summary.json"
    write_query_results(results_path, results)
    write_retrieval_run_summary(summary_path, summary)

    loaded_results = load_query_results(results_path)
    loaded_summary = load_retrieval_run_summary(summary_path)
    assert [row.to_dict() for row in loaded_results] == [row.to_dict() for row in results]
    assert loaded_summary.to_dict() == summary.to_dict()


def test_default_retrieval_run_paths_are_deterministic() -> None:
    metadata = _build_fixture_metadata()
    run_id = build_retrieval_run_id(
        metadata=metadata,
        retriever_name="dense-faiss",
        retriever_type="dense",
        top_k=DEFAULT_EVAL_TOP_K,
    )
    assert run_id == "snap-1-v1-dense-dense-faiss-top5"

    results_path, summary_path = default_retrieval_run_paths(
        metadata=metadata,
        retriever_name="dense-faiss",
        retriever_type="dense",
        top_k=DEFAULT_EVAL_TOP_K,
        repo_root=Path("/repo"),
    )
    assert results_path == Path(
        "/repo/data/evaluation/runs/snap-1-v1-dense-dense-faiss-top5.results.jsonl"
    )
    assert summary_path == Path(
        "/repo/data/evaluation/runs/snap-1-v1-dense-dense-faiss-top5.summary.json"
    )


def test_hybrid_rrf_merges_duplicate_hits_deterministically() -> None:
    entry = _build_fixture_entries()[0]

    dense = StaticEvaluationRetriever(
        name="dense",
        retriever_type="dense",
        hits_by_query_id={
            "q1": [
                RetrievalHit(
                    chunk_id="chunk-b", score=0.9, rank=1, doc_id="doc-a", section_id="sec-a"
                ),
                RetrievalHit(
                    chunk_id="chunk-a", score=0.8, rank=2, doc_id="doc-a", section_id="sec-a"
                ),
            ]
        },
    )
    lexical = StaticEvaluationRetriever(
        name="bm25",
        retriever_type="bm25",
        hits_by_query_id={
            "q1": [
                RetrievalHit(
                    chunk_id="chunk-a", score=4.0, rank=1, doc_id="doc-a", section_id="sec-a"
                ),
                RetrievalHit(
                    chunk_id="chunk-noise", score=2.0, rank=2, doc_id="doc-b", section_id="sec-b"
                ),
            ]
        },
    )

    retriever = HybridRRFEvaluationRetriever(
        dense_retriever=dense,
        lexical_retriever=lexical,
        rrf_k=10,
        candidate_depth=5,
    )
    hits = retriever.retrieve(entry, top_k=3)

    assert [hit.chunk_id for hit in hits] == ["chunk-a", "chunk-b", "chunk-noise"]
    assert hits[0].rank == 1
    assert hits[0].metadata == {"dense_rank": 2, "bm25_rank": 1}


def test_cli_evaluate_retrieval_static_fixture_writes_artifacts(tmp_path: Path) -> None:
    entries = _build_fixture_entries()
    metadata = _build_fixture_metadata()
    registry = _build_fixture_registry()
    dataset_path, metadata_path, registry_path = _write_dev_qa_fixture_files(
        tmp_path,
        entries=entries,
        metadata=metadata,
        registry=registry,
    )

    results_output = tmp_path / "cli.results.jsonl"
    summary_output = tmp_path / "cli.summary.json"
    exit_code = main(
        [
            "evaluate-retrieval",
            "--dataset",
            str(dataset_path),
            "--metadata",
            str(metadata_path),
            "--registry",
            str(registry_path),
            "--retriever-kind",
            "static",
            "--fixture-name",
            "oracle",
            "--results-output",
            str(results_output),
            "--summary-output",
            str(summary_output),
        ]
    )

    assert exit_code == 0
    assert results_output.is_file()
    assert summary_output.is_file()

    loaded_results = load_query_results(results_output)
    loaded_summary = load_retrieval_run_summary(summary_output)
    assert len(loaded_results) == len(entries)
    assert loaded_summary.hit_at_k == 1.0
    assert loaded_summary.mrr == 1.0


def test_bm25_retriever_scores_expected_chunk_from_tiny_fixture(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "doc_id": "doc-a",
                        "chunk_id": "chunk-a",
                        "section_id": "sec-a",
                        "section_index": 0,
                        "chunk_index": 0,
                        "doc_title": "Services",
                        "section_path": ["Services"],
                        "source_path": "docs/services.md",
                        "source_url": "https://example.test/services",
                        "license": "CC BY 4.0",
                        "attribution": "Example",
                        "language": "en",
                        "start_offset": 0,
                        "end_offset": 10,
                        "token_count": 6,
                        "text": "A Kubernetes Service gives stable networking in front of Pods.",
                    }
                ),
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "doc_id": "doc-b",
                        "chunk_id": "chunk-b",
                        "section_id": "sec-b",
                        "section_index": 0,
                        "chunk_index": 0,
                        "doc_title": "Probes",
                        "section_path": ["Probes"],
                        "source_path": "docs/probes.md",
                        "source_url": "https://example.test/probes",
                        "license": "CC BY 4.0",
                        "attribution": "Example",
                        "language": "en",
                        "start_offset": 0,
                        "end_offset": 10,
                        "token_count": 6,
                        "text": "Readiness probes control traffic routing to containers.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    retriever = BM25ChunkEvaluationRetriever(chunks_path=chunks_path)
    entry = _build_fixture_entries()[0]
    hits = retriever.retrieve(entry, top_k=2)
    assert hits
    assert hits[0].chunk_id == "chunk-a"
