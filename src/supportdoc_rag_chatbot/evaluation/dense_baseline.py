from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from supportdoc_rag_chatbot.retrieval.embeddings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DEVICE,
    create_local_embedder,
    load_chunk_records,
)
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
    load_faiss_index_backend,
    read_index_metadata,
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
from .harness import RetrievalHit, evaluate_retriever

DEFAULT_DENSE_BASELINE_TOP_K = 5
DEFAULT_DENSE_BASELINE_LABEL = "default"


@dataclass(slots=True)
class DenseBaselineConfig:
    index_path: Path = DEFAULT_FAISS_INDEX_PATH
    index_metadata_path: Path = DEFAULT_FAISS_METADATA_PATH
    row_mapping_path: Path | None = None
    dataset_path: Path | None = None
    dataset_metadata_path: Path | None = None
    registry_path: Path | None = None
    model_name: str | None = None
    device: str = DEFAULT_DEVICE
    batch_size: int = DEFAULT_BATCH_SIZE
    top_k: int = DEFAULT_DENSE_BASELINE_TOP_K
    run_name: str | None = None
    run_label: str = DEFAULT_DENSE_BASELINE_LABEL
    results_output_path: Path | None = None
    summary_output_path: Path | None = None


class DenseBaselineRetriever:
    name = "dense"
    retriever_type = "dense"

    def __init__(self, config: DenseBaselineConfig) -> None:
        if config.top_k <= 0:
            raise ValueError("top_k must be > 0")

        index_metadata = read_index_metadata(config.index_metadata_path)
        self.backend = load_faiss_index_backend(
            index_path=config.index_path,
            metadata_path=config.index_metadata_path,
            row_mapping_path=config.row_mapping_path,
        )
        self.model_name = config.model_name or index_metadata.embedding_model_name
        self.index_backend_name = index_metadata.backend_name
        self.embedder = create_local_embedder(
            model_name=self.model_name,
            device=config.device,
            batch_size=config.batch_size,
            normalize_embeddings=True,
        )
        self.chunk_info_by_id = {
            chunk.chunk_id: chunk
            for chunk in load_chunk_records(Path(index_metadata.source_chunks_path))
        }
        self.config = {
            "embedding_model_name": self.model_name,
            "index_backend": self.index_backend_name,
            "top_k": config.top_k,
            "index_path": str(config.index_path),
            "index_metadata_path": str(config.index_metadata_path),
        }

    def retrieve(self, entry: DevQAEntry, *, top_k: int) -> list[RetrievalHit]:
        normalized_query = " ".join(entry.question.split())
        if not normalized_query:
            return []

        query_vectors = self.embedder.embed_texts([normalized_query])
        if len(query_vectors) != 1:
            raise ValueError(
                f"Embedding backend returned {len(query_vectors)} rows for a single query"
            )

        results = self.backend.search(query_vectors[0], top_k=top_k)
        hits: list[RetrievalHit] = []
        for result in results:
            chunk = self.chunk_info_by_id.get(result.chunk_id)
            hits.append(
                RetrievalHit(
                    chunk_id=result.chunk_id,
                    score=float(result.score),
                    rank=int(result.rank),
                    doc_id=(chunk.doc_id if chunk is not None else None),
                    section_id=(chunk.section_id if chunk is not None else None),
                )
            )
        return hits


def run_dense_baseline(config: DenseBaselineConfig | None = None) -> RetrievalRunArtifacts:
    runtime_config = config or DenseBaselineConfig()

    dataset_entries, dataset_metadata = _load_dataset_surface(runtime_config)
    registry = _load_registry_surface(runtime_config, dataset_metadata)
    retriever = DenseBaselineRetriever(runtime_config)

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


def render_dense_baseline_report(run: RetrievalRunArtifacts) -> str:
    summary = run.summary
    config = summary.retriever_config
    lines = [
        "Dense retrieval baseline",
        f"run_name: {summary.run_name}",
        f"dataset: {summary.dataset_name}:{summary.dataset_version}",
        f"snapshot_id: {summary.snapshot_id}",
        f"embedding_model: {config.get('embedding_model_name', '(unknown)')}",
        f"index_backend: {config.get('index_backend', '(unknown)')}",
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
    config: DenseBaselineConfig,
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
    config: DenseBaselineConfig,
    metadata: DevQAMetadata,
) -> EvidenceRegistry:
    if config.registry_path is not None:
        return load_evidence_registry(config.registry_path)

    if config.dataset_path is None and config.dataset_metadata_path is None:
        return load_default_evidence_registry()

    entries = (
        load_default_dev_qa_dataset()
        if config.dataset_path is None
        else load_dev_qa_dataset(config.dataset_path)
    )
    index_metadata = read_index_metadata(config.index_metadata_path)
    chunks = load_chunk_records(Path(index_metadata.source_chunks_path))

    chunk_doc_ids = sorted({chunk.doc_id for chunk in chunks})
    entry_doc_ids = sorted({doc_id for entry in entries for doc_id in entry.doc_ids})
    chunk_section_ids = sorted({chunk.section_id for chunk in chunks})
    entry_section_ids = sorted(
        {section_id for entry in entries for section_id in entry.expected_section_ids}
    )
    chunk_ids = sorted({chunk.chunk_id for chunk in chunks})
    entry_chunk_ids = sorted(
        {chunk_id for entry in entries for chunk_id in entry.expected_chunk_ids}
    )

    return EvidenceRegistry(
        snapshot_id=metadata.snapshot_id,
        source_manifest_path=metadata.source_manifest_path,
        doc_ids=_select_ids(
            expected_count=metadata.doc_count, primary=entry_doc_ids, fallback=chunk_doc_ids
        ),
        section_ids=_select_ids(
            expected_count=metadata.section_id_count,
            primary=entry_section_ids,
            fallback=chunk_section_ids,
        ),
        chunk_ids=_select_ids(
            expected_count=metadata.chunk_id_count, primary=chunk_ids, fallback=entry_chunk_ids
        ),
        default_chunking=dict(metadata.default_chunking),
    )


def _default_run_name(*, metadata: DevQAMetadata, top_k: int, label: str) -> str:
    return f"dense-{metadata.snapshot_id}-{metadata.dataset_version}-top{top_k}-{label}"


def _resolve_output_paths(
    *,
    config: DenseBaselineConfig,
    dataset_metadata: DevQAMetadata,
) -> tuple[Path, Path]:
    if config.results_output_path is not None and config.summary_output_path is not None:
        return config.results_output_path, config.summary_output_path

    run_name = config.run_name or _default_run_name(
        metadata=dataset_metadata,
        top_k=config.top_k,
        label=config.run_label,
    )
    default_dataset_path, _, _ = default_dev_qa_paths()
    repo_root = default_dataset_path.parents[2]

    results_output_path = config.results_output_path or (
        repo_root / "data" / "evaluation" / "runs" / f"{run_name}.results.jsonl"
    )
    summary_output_path = config.summary_output_path or (
        repo_root / "data" / "evaluation" / "runs" / f"{run_name}.summary.json"
    )
    return results_output_path, summary_output_path


def _select_ids(*, expected_count: int, primary: list[str], fallback: list[str]) -> list[str]:
    if len(primary) == expected_count:
        return primary
    if len(fallback) == expected_count:
        return fallback
    if primary:
        return primary
    return fallback
