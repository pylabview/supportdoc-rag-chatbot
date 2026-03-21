from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from supportdoc_rag_chatbot.evaluation import (
    DEFAULT_EVAL_TOP_K,
    DEFAULT_HYBRID_CANDIDATE_DEPTH,
    DEFAULT_RRF_K,
    BM25ChunkEvaluationRetriever,
    DenseFaissEvaluationRetriever,
    HybridRRFEvaluationRetriever,
    create_dev_qa_fixture_retriever,
    default_dev_qa_paths,
    default_retrieval_run_paths,
    evaluate_retriever,
    load_dev_qa_dataset,
    load_dev_qa_metadata,
    load_evidence_registry,
    render_retrieval_evaluation_report,
    write_query_results,
    write_retrieval_run_summary,
)
from supportdoc_rag_chatbot.retrieval.embeddings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHUNKS_PATH,
    DEFAULT_DEVICE,
    DEFAULT_LOCAL_EMBEDDING_MODEL,
    DEFAULT_METADATA_PATH,
    DEFAULT_VECTORS_PATH,
    build_embedding_artifacts,
    create_local_embedder,
)
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
    DEFAULT_FAISS_ROW_MAPPING_PATH,
    build_faiss_index_artifacts,
)
from supportdoc_rag_chatbot.retrieval.smoke import (
    DEFAULT_PREVIEW_CHARS,
    DEFAULT_RETRIEVAL_TOP_K,
    render_dense_retrieval_smoke_report,
    run_dense_retrieval_smoke,
)

DEFAULT_DEV_QA_DATASET_PATH, DEFAULT_DEV_QA_METADATA_PATH, DEFAULT_DEV_QA_REGISTRY_PATH = (
    default_dev_qa_paths()
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="supportdoc-rag-chatbot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    embed_parser = subparsers.add_parser(
        "embed-chunks",
        help="Generate local dense embedding artifacts from chunks.jsonl",
    )
    embed_parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CHUNKS_PATH,
        help="Path to chunks.jsonl (default: data/processed/chunks.jsonl)",
    )
    embed_parser.add_argument(
        "--vectors-output",
        type=Path,
        default=DEFAULT_VECTORS_PATH,
        help="Output path for the row-major float32 vector artifact",
    )
    embed_parser.add_argument(
        "--metadata-output",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help="Output path for the embedding metadata JSON",
    )
    embed_parser.add_argument(
        "--model-name",
        default=DEFAULT_LOCAL_EMBEDDING_MODEL,
        help="Local embedding model name or path",
    )
    embed_parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help="Embedding device, for example cpu, cuda, or mps",
    )
    embed_parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Embedding batch size",
    )
    embed_parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Disable L2 normalization on output vectors",
    )
    embed_parser.set_defaults(handler=_run_embed_chunks)

    index_parser = subparsers.add_parser(
        "build-faiss-index",
        help="Build and persist a local FAISS index from saved embedding artifacts",
    )
    index_parser.add_argument(
        "--embedding-metadata",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help="Path to the embedding metadata JSON produced by embed-chunks",
    )
    index_parser.add_argument(
        "--index-output",
        type=Path,
        default=DEFAULT_FAISS_INDEX_PATH,
        help="Output path for the persisted FAISS index file",
    )
    index_parser.add_argument(
        "--index-metadata-output",
        type=Path,
        default=DEFAULT_FAISS_METADATA_PATH,
        help="Output path for the FAISS index metadata JSON",
    )
    index_parser.add_argument(
        "--row-mapping-output",
        type=Path,
        default=DEFAULT_FAISS_ROW_MAPPING_PATH,
        help="Output path for the row-to-chunk-id mapping JSON",
    )
    index_parser.set_defaults(handler=_run_build_faiss_index)

    smoke_parser = subparsers.add_parser(
        "smoke-dense-retrieval",
        help="Run a local dense-retrieval smoke test over the saved FAISS index",
    )
    smoke_parser.add_argument(
        "--query",
        required=True,
        help="Query text to embed and search",
    )
    smoke_parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_RETRIEVAL_TOP_K,
        help="Number of top matches to print",
    )
    smoke_parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_FAISS_INDEX_PATH,
        help="Path to the persisted FAISS index file",
    )
    smoke_parser.add_argument(
        "--index-metadata",
        type=Path,
        default=DEFAULT_FAISS_METADATA_PATH,
        help="Path to the FAISS index metadata JSON",
    )
    smoke_parser.add_argument(
        "--row-mapping",
        type=Path,
        default=None,
        help="Optional path to the row-to-chunk-id mapping JSON (defaults to the metadata sidecar)",
    )
    smoke_parser.add_argument(
        "--chunks",
        type=Path,
        default=None,
        help=(
            "Optional path to chunks.jsonl (defaults to the source path recorded in index metadata)"
        ),
    )
    smoke_parser.add_argument(
        "--model-name",
        default=None,
        help="Optional embedding model override (defaults to the model recorded in index metadata)",
    )
    smoke_parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help="Embedding device, for example cpu, cuda, or mps",
    )
    smoke_parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Embedding batch size for the single-query embedder",
    )
    smoke_parser.add_argument(
        "--preview-chars",
        type=int,
        default=DEFAULT_PREVIEW_CHARS,
        help="Maximum number of characters to print from each chunk preview",
    )
    smoke_parser.set_defaults(handler=_run_smoke_dense_retrieval)

    eval_parser = subparsers.add_parser(
        "evaluate-retrieval",
        help="Run a retriever against the dev QA set and write evaluation artifacts",
    )
    eval_parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DEV_QA_DATASET_PATH,
        help="Path to the dev QA dataset JSONL",
    )
    eval_parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_DEV_QA_METADATA_PATH,
        help="Path to the dev QA metadata JSON",
    )
    eval_parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_DEV_QA_REGISTRY_PATH,
        help="Path to the dev QA evidence registry JSON",
    )
    eval_parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_EVAL_TOP_K,
        help="Number of ranked hits to keep per query",
    )
    eval_parser.add_argument(
        "--results-output",
        type=Path,
        default=None,
        help="Optional output path for the per-query retrieval results JSONL",
    )
    eval_parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional output path for the summary metrics JSON",
    )
    eval_parser.add_argument(
        "--retriever-kind",
        choices=["static", "dense", "bm25", "hybrid"],
        required=True,
        help="Retriever implementation to execute",
    )
    eval_parser.add_argument(
        "--retriever-name",
        default=None,
        help="Optional retriever name override recorded in the run artifacts",
    )
    eval_parser.add_argument(
        "--fixture-name",
        default="oracle",
        help="Fixture behavior for --retriever-kind static (oracle, first-gold, empty)",
    )
    eval_parser.add_argument(
        "--fixture-retriever-type",
        default="fixture",
        help="Logical retriever type recorded for static fixtures",
    )
    eval_parser.add_argument(
        "--chunks",
        type=Path,
        default=None,
        help="Path to chunks.jsonl for BM25 / hybrid runs (dense can infer this from index metadata)",
    )
    eval_parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_FAISS_INDEX_PATH,
        help="Path to the persisted FAISS index file for dense / hybrid runs",
    )
    eval_parser.add_argument(
        "--index-metadata",
        type=Path,
        default=DEFAULT_FAISS_METADATA_PATH,
        help="Path to the FAISS index metadata JSON for dense / hybrid runs",
    )
    eval_parser.add_argument(
        "--row-mapping",
        type=Path,
        default=None,
        help="Optional FAISS row mapping override for dense / hybrid runs",
    )
    eval_parser.add_argument(
        "--model-name",
        default=None,
        help="Optional embedding model override for dense / hybrid query embedding",
    )
    eval_parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help="Embedding device for dense / hybrid query embedding",
    )
    eval_parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Embedding batch size for dense / hybrid query embedding",
    )
    eval_parser.add_argument(
        "--rrf-k",
        type=int,
        default=DEFAULT_RRF_K,
        help="Reciprocal-rank-fusion constant for hybrid retrieval",
    )
    eval_parser.add_argument(
        "--candidate-depth",
        type=int,
        default=DEFAULT_HYBRID_CANDIDATE_DEPTH,
        help="Candidate depth per component retriever before hybrid fusion",
    )
    eval_parser.set_defaults(handler=_run_evaluate_retrieval)

    return parser


def _run_embed_chunks(args: argparse.Namespace) -> int:
    embedder = create_local_embedder(
        model_name=args.model_name,
        device=args.device,
        batch_size=args.batch_size,
        normalize_embeddings=not args.no_normalize,
    )
    metadata = build_embedding_artifacts(
        chunks_path=args.input,
        vectors_path=args.vectors_output,
        metadata_path=args.metadata_output,
        embedder=embedder,
        batch_size=args.batch_size,
    )
    print(
        "Wrote embedding artifacts: "
        f"rows={metadata.row_count}, dim={metadata.vector_dimension}, "
        f"vectors={args.vectors_output}, metadata={args.metadata_output}"
    )
    return 0


def _run_build_faiss_index(args: argparse.Namespace) -> int:
    metadata = build_faiss_index_artifacts(
        embedding_metadata_path=args.embedding_metadata,
        index_path=args.index_output,
        metadata_path=args.index_metadata_output,
        row_mapping_path=args.row_mapping_output,
    )
    print(
        "Wrote FAISS index artifacts: "
        f"rows={metadata.row_count}, dim={metadata.vector_dimension}, "
        f"index={args.index_output}, metadata={args.index_metadata_output}, "
        f"row-mapping={args.row_mapping_output}"
    )
    return 0


def _run_smoke_dense_retrieval(args: argparse.Namespace) -> int:
    report = run_dense_retrieval_smoke(
        query_text=args.query,
        top_k=args.top_k,
        index_path=args.index,
        index_metadata_path=args.index_metadata,
        row_mapping_path=args.row_mapping,
        chunks_path=args.chunks,
        model_name=args.model_name,
        device=args.device,
        batch_size=args.batch_size,
        preview_chars=args.preview_chars,
    )
    print(render_dense_retrieval_smoke_report(report))
    return 0


def _run_evaluate_retrieval(args: argparse.Namespace) -> int:
    entries = load_dev_qa_dataset(args.dataset)
    metadata = load_dev_qa_metadata(args.metadata)
    registry = load_evidence_registry(args.registry)

    retriever = _build_evaluation_retriever(args, entries=entries)
    results, summary = evaluate_retriever(
        retriever=retriever,
        entries=entries,
        metadata=metadata,
        registry=registry,
        top_k=args.top_k,
    )

    default_results_output, default_summary_output = default_retrieval_run_paths(
        metadata=metadata,
        retriever_name=summary.retriever_name,
        retriever_type=summary.retriever_type,
        top_k=summary.top_k,
    )
    results_output = args.results_output or default_results_output
    summary_output = args.summary_output or default_summary_output

    write_query_results(results_output, results)
    write_retrieval_run_summary(summary_output, summary)
    print(
        render_retrieval_evaluation_report(
            summary,
            results_path=results_output,
            summary_path=summary_output,
        )
    )
    return 0


def _build_evaluation_retriever(
    args: argparse.Namespace,
    *,
    entries: list,
):
    if args.retriever_kind == "static":
        return create_dev_qa_fixture_retriever(
            entries,
            fixture_name=args.fixture_name,
            name=args.retriever_name,
            retriever_type=args.fixture_retriever_type,
        )
    if args.retriever_kind == "dense":
        return DenseFaissEvaluationRetriever(
            name=args.retriever_name or "dense-faiss",
            index_path=args.index,
            index_metadata_path=args.index_metadata,
            row_mapping_path=args.row_mapping,
            chunks_path=args.chunks,
            model_name=args.model_name,
            device=args.device,
            batch_size=args.batch_size,
        )
    if args.retriever_kind == "bm25":
        return BM25ChunkEvaluationRetriever(
            name=args.retriever_name or "bm25",
            chunks_path=args.chunks or DEFAULT_CHUNKS_PATH,
        )
    if args.retriever_kind == "hybrid":
        dense_retriever = DenseFaissEvaluationRetriever(
            name="dense-faiss",
            index_path=args.index,
            index_metadata_path=args.index_metadata,
            row_mapping_path=args.row_mapping,
            chunks_path=args.chunks,
            model_name=args.model_name,
            device=args.device,
            batch_size=args.batch_size,
        )
        lexical_retriever = BM25ChunkEvaluationRetriever(
            name="bm25",
            chunks_path=args.chunks or DEFAULT_CHUNKS_PATH,
        )
        return HybridRRFEvaluationRetriever(
            dense_retriever=dense_retriever,
            lexical_retriever=lexical_retriever,
            name=args.retriever_name or "hybrid-rrf",
            rrf_k=args.rrf_k,
            candidate_depth=args.candidate_depth,
        )
    raise ValueError(f"Unsupported retriever kind: {args.retriever_kind}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        handler = args.handler
    except AttributeError as exc:  # pragma: no cover - argparse enforces this already
        raise RuntimeError("No command selected") from exc

    try:
        return int(handler(args))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
