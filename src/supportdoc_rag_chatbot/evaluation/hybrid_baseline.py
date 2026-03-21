from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from supportdoc_rag_chatbot.retrieval.embeddings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHUNKS_PATH,
    DEFAULT_DEVICE,
    load_chunk_records,
)
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
)

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
from .retrievers import (
    DEFAULT_HYBRID_CANDIDATE_DEPTH,
    DEFAULT_RRF_K,
    BM25ChunkEvaluationRetriever,
    DenseFaissEvaluationRetriever,
    HybridRRFEvaluationRetriever,
)

DEFAULT_HYBRID_BASELINE_TOP_K = 5
DEFAULT_HYBRID_BASELINE_LABEL = "default"


@dataclass(slots=True)
class HybridBaselineConfig:
    chunks_path: Path = DEFAULT_CHUNKS_PATH
    index_path: Path = DEFAULT_FAISS_INDEX_PATH
    index_metadata_path: Path = DEFAULT_FAISS_METADATA_PATH
    row_mapping_path: Path | None = None
    dataset_path: Path | None = None
    dataset_metadata_path: Path | None = None
    registry_path: Path | None = None
    model_name: str | None = None
    device: str = DEFAULT_DEVICE
    batch_size: int = DEFAULT_BATCH_SIZE
    rrf_k: int = DEFAULT_RRF_K
    candidate_depth: int = DEFAULT_HYBRID_CANDIDATE_DEPTH
    top_k: int = DEFAULT_HYBRID_BASELINE_TOP_K
    run_name: str | None = None
    run_label: str = DEFAULT_HYBRID_BASELINE_LABEL
    results_output_path: Path | None = None
    summary_output_path: Path | None = None


class HybridBaselineRetriever(HybridRRFEvaluationRetriever):
    def __init__(self, config: HybridBaselineConfig) -> None:
        if config.top_k <= 0:
            raise ValueError("top_k must be > 0")
        dense_retriever = DenseFaissEvaluationRetriever(
            name="dense-faiss",
            index_path=config.index_path,
            index_metadata_path=config.index_metadata_path,
            row_mapping_path=config.row_mapping_path,
            chunks_path=config.chunks_path,
            model_name=config.model_name,
            device=config.device,
            batch_size=config.batch_size,
        )
        lexical_retriever = BM25ChunkEvaluationRetriever(
            name="bm25",
            chunks_path=config.chunks_path,
        )
        super().__init__(
            dense_retriever=dense_retriever,
            lexical_retriever=lexical_retriever,
            name="hybrid-rrf",
            rrf_k=config.rrf_k,
            candidate_depth=config.candidate_depth,
        )


def run_hybrid_baseline(config: HybridBaselineConfig | None = None) -> RetrievalRunArtifacts:
    runtime_config = config or HybridBaselineConfig()

    dataset_entries, dataset_metadata = _load_dataset_surface(runtime_config)
    registry = _load_registry_surface(runtime_config, dataset_metadata)
    retriever = HybridBaselineRetriever(runtime_config)

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


def render_hybrid_baseline_report(run: RetrievalRunArtifacts) -> str:
    summary = run.summary
    config = summary.retriever_config
    lines = [
        "Hybrid retrieval baseline",
        f"run_name: {summary.run_name}",
        f"dataset: {summary.dataset_name}:{summary.dataset_version}",
        f"snapshot_id: {summary.snapshot_id}",
        f"fusion_strategy: {config.get('fusion_strategy_name', '(unknown)')}",
        f"rrf_k: {config.get('rrf_k', '(unknown)')}",
        f"candidate_depth: {config.get('candidate_depth', '(unknown)')}",
        f"dense_retriever: {config.get('dense_retriever', '(unknown)')}",
        f"lexical_retriever: {config.get('lexical_retriever', '(unknown)')}",
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
    config: HybridBaselineConfig,
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
    config: HybridBaselineConfig,
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
    config: HybridBaselineConfig,
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
    return f"hybrid-rrf-{metadata.snapshot_id}-{metadata.dataset_version}-top{top_k}-{label}"
