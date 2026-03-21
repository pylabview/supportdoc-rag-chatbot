from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from supportdoc_rag_chatbot.retrieval.embeddings import DEFAULT_CHUNKS_PATH, load_chunk_records

from .artifacts import (
    RetrievalQueryArtifact,
    RetrievalRunArtifacts,
    RetrievalSummaryArtifact,
    RetrievedChunkArtifact,
    write_retrieval_results,
    write_retrieval_summary,
)
from .dev_qa import (
    DevQAEntry,
    DevQAMetadata,
    EvidenceRegistry,
    default_dev_qa_paths,
    load_default_dev_qa_dataset,
    load_default_dev_qa_metadata,
    load_default_evidence_registry,
    load_dev_qa_dataset,
    load_dev_qa_metadata,
    load_evidence_registry,
)
from .harness import evaluate_retriever
from .retrievers import BM25ChunkEvaluationRetriever

DEFAULT_BM25_BASELINE_TOP_K = 5
DEFAULT_BM25_BASELINE_LABEL = "default"
DEFAULT_BM25_K1 = 1.5
DEFAULT_BM25_B = 0.75


@dataclass(slots=True)
class BM25BaselineConfig:
    chunks_path: Path = DEFAULT_CHUNKS_PATH
    dataset_path: Path | None = None
    dataset_metadata_path: Path | None = None
    registry_path: Path | None = None
    k1: float = DEFAULT_BM25_K1
    b: float = DEFAULT_BM25_B
    top_k: int = DEFAULT_BM25_BASELINE_TOP_K
    run_name: str | None = None
    run_label: str = DEFAULT_BM25_BASELINE_LABEL
    results_output_path: Path | None = None
    summary_output_path: Path | None = None


class BM25BaselineRetriever(BM25ChunkEvaluationRetriever):
    def __init__(self, config: BM25BaselineConfig) -> None:
        if config.top_k <= 0:
            raise ValueError("top_k must be > 0")
        super().__init__(
            chunks_path=config.chunks_path,
            name="bm25",
            k1=config.k1,
            b=config.b,
        )


def run_bm25_baseline(config: BM25BaselineConfig | None = None) -> RetrievalRunArtifacts:
    runtime_config = config or BM25BaselineConfig()

    dataset_entries, dataset_metadata = _load_dataset_surface(runtime_config)
    registry = _load_registry_surface(runtime_config, dataset_metadata)
    retriever = BM25BaselineRetriever(runtime_config)

    results_output_path, summary_output_path = _resolve_output_paths(
        config=runtime_config,
        dataset_metadata=dataset_metadata,
    )
    run_name = runtime_config.run_name or _default_run_name(
        metadata=dataset_metadata,
        top_k=runtime_config.top_k,
        label=runtime_config.run_label,
    )

    harness_results, harness_summary = evaluate_retriever(
        retriever=retriever,
        entries=dataset_entries,
        metadata=dataset_metadata,
        registry=registry,
        top_k=runtime_config.top_k,
    )

    result_artifacts = [
        RetrievalQueryArtifact(
            query_id=result.query_id,
            question=result.question,
            answerable=result.answerable,
            snapshot_id=result.snapshot_id,
            retriever_name=result.retriever_name,
            top_k=result.top_k,
            latency_ms=result.latency_ms,
            expected_chunk_ids=list(result.expected_chunk_ids),
            matches=[
                RetrievedChunkArtifact(
                    chunk_id=hit.chunk_id,
                    rank=hit.rank,
                    score=hit.score,
                )
                for hit in result.hits
            ],
            retriever_config=dict(result.retriever_config),
        )
        for result in harness_results
    ]

    summary_artifact = RetrievalSummaryArtifact(
        run_name=run_name,
        dataset_name=dataset_metadata.dataset_name,
        dataset_version=dataset_metadata.dataset_version,
        snapshot_id=dataset_metadata.snapshot_id,
        retriever_name=harness_summary.retriever_name,
        top_k=harness_summary.top_k,
        query_count=harness_summary.total_query_count,
        answerable_query_count=harness_summary.answerable_query_count,
        hit_at_k=harness_summary.hit_at_k,
        recall_at_k=harness_summary.recall_at_k,
        mrr=harness_summary.mrr,
        mean_latency_ms=harness_summary.average_latency_ms,
        max_latency_ms=harness_summary.max_latency_ms,
        results_output_path=str(results_output_path),
        summary_output_path=str(summary_output_path),
        retriever_config=dict(harness_summary.retriever_config),
    )

    write_retrieval_results(results_output_path, result_artifacts)
    write_retrieval_summary(summary_output_path, summary_artifact)
    return RetrievalRunArtifacts(results=result_artifacts, summary=summary_artifact)


def render_bm25_baseline_report(run: RetrievalRunArtifacts) -> str:
    summary = run.summary
    config = summary.retriever_config
    lines = [
        "BM25 retrieval baseline",
        f"run_name: {summary.run_name}",
        f"dataset: {summary.dataset_name}:{summary.dataset_version}",
        f"snapshot_id: {summary.snapshot_id}",
        f"chunks_path: {config.get('chunks_path', '(unknown)')}",
        f"tokenization: {config.get('tokenization', '(unknown)')}",
        f"k1: {config.get('k1', '(unknown)')}",
        f"b: {config.get('b', '(unknown)')}",
        f"top_k: {summary.top_k}",
        f"query_count: {summary.query_count}",
        f"answerable_query_count: {summary.answerable_query_count}",
        f"hit@k: {summary.hit_at_k:.6f}",
        f"recall@k: {summary.recall_at_k:.6f}",
        f"mrr: {summary.mrr:.6f}",
        f"mean_latency_ms: {summary.mean_latency_ms:.3f}",
        f"max_latency_ms: {summary.max_latency_ms:.3f}",
        f"results_output: {summary.results_output_path}",
        f"summary_output: {summary.summary_output_path}",
    ]
    return "\n".join(lines)


def _load_dataset_surface(
    config: BM25BaselineConfig,
) -> tuple[list[DevQAEntry], DevQAMetadata]:
    if config.dataset_path is None:
        dataset_entries = load_default_dev_qa_dataset()
    else:
        dataset_entries = load_dev_qa_dataset(config.dataset_path)

    if config.dataset_metadata_path is None:
        dataset_metadata = load_default_dev_qa_metadata()
    else:
        dataset_metadata = load_dev_qa_metadata(config.dataset_metadata_path)

    return dataset_entries, dataset_metadata


def _load_registry_surface(
    config: BM25BaselineConfig,
    metadata: DevQAMetadata,
) -> EvidenceRegistry:
    if config.registry_path is not None:
        return load_evidence_registry(config.registry_path)

    if config.dataset_path is None and config.dataset_metadata_path is None:
        return load_default_evidence_registry()

    chunks = load_chunk_records(config.chunks_path)
    return EvidenceRegistry(
        snapshot_id=metadata.snapshot_id,
        source_manifest_path=metadata.source_manifest_path,
        doc_ids=sorted({chunk.doc_id for chunk in chunks}),
        section_ids=sorted({chunk.section_id for chunk in chunks}),
        chunk_ids=sorted({chunk.chunk_id for chunk in chunks}),
        default_chunking=dict(metadata.default_chunking),
    )


def _resolve_output_paths(
    *,
    config: BM25BaselineConfig,
    dataset_metadata: DevQAMetadata,
) -> tuple[Path, Path]:
    results_output_path = config.results_output_path
    summary_output_path = config.summary_output_path

    if results_output_path is not None and summary_output_path is not None:
        return results_output_path, summary_output_path

    default_dataset_path, _, _ = default_dev_qa_paths()
    repo_root = default_dataset_path.parents[2]
    run_name = config.run_name or _default_run_name(
        metadata=dataset_metadata,
        top_k=config.top_k,
        label=config.run_label,
    )

    if results_output_path is None:
        results_output_path = (
            repo_root / "data" / "evaluation" / "runs" / f"{run_name}.results.jsonl"
        )
    if summary_output_path is None:
        summary_output_path = (
            repo_root / "data" / "evaluation" / "runs" / f"{run_name}.summary.json"
        )
    return results_output_path, summary_output_path


def _default_run_name(*, metadata: DevQAMetadata, top_k: int, label: str) -> str:
    return f"bm25-{metadata.snapshot_id}-{metadata.dataset_version}-top{top_k}-{label}"
