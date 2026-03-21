from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Callable, Iterable, Protocol

from supportdoc_rag_chatbot.ingestion.jsonl import read_jsonl, write_jsonl

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
    validate_dev_qa_dataset,
)

EVAL_ARTIFACT_VERSION = "v1"
DEFAULT_EVAL_TOP_K = 5
DEFAULT_RUNS_DIR = Path("data/evaluation/runs")
RESULTS_FILENAME_SUFFIX = ".results.jsonl"
SUMMARY_FILENAME_SUFFIX = ".summary.json"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class RetrievalHit:
    chunk_id: str
    score: float
    rank: int
    doc_id: str | None = None
    section_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalHit":
        metadata_payload = payload.get("metadata", {})
        if not isinstance(metadata_payload, dict):
            raise ValueError("RetrievalHit.metadata must be an object")
        return cls(
            chunk_id=str(payload["chunk_id"]),
            score=float(payload["score"]),
            rank=int(payload["rank"]),
            doc_id=(str(payload["doc_id"]) if payload.get("doc_id") is not None else None),
            section_id=(
                str(payload["section_id"]) if payload.get("section_id") is not None else None
            ),
            metadata=dict(metadata_payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QueryRetrievalResult:
    artifact_version: str
    run_id: str
    dataset_name: str
    dataset_version: str
    snapshot_id: str
    retriever_name: str
    retriever_type: str
    retriever_config: dict[str, Any]
    query_id: str
    question: str
    answerable: bool
    category: str
    tags: list[str]
    top_k: int
    latency_ms: float
    relevant_identifier_kind: str | None
    relevant_identifier_count: int
    matched_relevant_count: int
    hit: bool
    reciprocal_rank: float
    recall: float
    expected_chunk_ids: list[str]
    expected_section_ids: list[str]
    hits: list[RetrievalHit]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "QueryRetrievalResult":
        retriever_config = payload.get("retriever_config", {})
        if not isinstance(retriever_config, dict):
            raise ValueError("QueryRetrievalResult.retriever_config must be an object")
        return cls(
            artifact_version=str(payload["artifact_version"]),
            run_id=str(payload["run_id"]),
            dataset_name=str(payload["dataset_name"]),
            dataset_version=str(payload["dataset_version"]),
            snapshot_id=str(payload["snapshot_id"]),
            retriever_name=str(payload["retriever_name"]),
            retriever_type=str(payload["retriever_type"]),
            retriever_config=dict(retriever_config),
            query_id=str(payload["query_id"]),
            question=str(payload["question"]),
            answerable=bool(payload["answerable"]),
            category=str(payload["category"]),
            tags=[str(tag) for tag in payload.get("tags", [])],
            top_k=int(payload["top_k"]),
            latency_ms=float(payload["latency_ms"]),
            relevant_identifier_kind=(
                str(payload["relevant_identifier_kind"])
                if payload.get("relevant_identifier_kind")
                else None
            ),
            relevant_identifier_count=int(payload["relevant_identifier_count"]),
            matched_relevant_count=int(payload["matched_relevant_count"]),
            hit=bool(payload["hit"]),
            reciprocal_rank=float(payload["reciprocal_rank"]),
            recall=float(payload["recall"]),
            expected_chunk_ids=[str(value) for value in payload.get("expected_chunk_ids", [])],
            expected_section_ids=[str(value) for value in payload.get("expected_section_ids", [])],
            hits=[RetrievalHit.from_dict(item) for item in payload.get("hits", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["hits"] = [hit.to_dict() for hit in self.hits]
        return payload


@dataclass(slots=True)
class RetrievalRunSummary:
    artifact_version: str
    run_id: str
    dataset_name: str
    dataset_version: str
    snapshot_id: str
    retriever_name: str
    retriever_type: str
    retriever_config: dict[str, Any]
    top_k: int
    total_query_count: int
    answerable_query_count: int
    unanswerable_query_count: int
    relevant_query_count: int
    query_with_results_count: int
    query_without_results_count: int
    hit_at_k: float
    recall_at_k: float
    mrr: float
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalRunSummary":
        retriever_config = payload.get("retriever_config", {})
        if not isinstance(retriever_config, dict):
            raise ValueError("RetrievalRunSummary.retriever_config must be an object")
        return cls(
            artifact_version=str(payload["artifact_version"]),
            run_id=str(payload["run_id"]),
            dataset_name=str(payload["dataset_name"]),
            dataset_version=str(payload["dataset_version"]),
            snapshot_id=str(payload["snapshot_id"]),
            retriever_name=str(payload["retriever_name"]),
            retriever_type=str(payload["retriever_type"]),
            retriever_config=dict(retriever_config),
            top_k=int(payload["top_k"]),
            total_query_count=int(payload["total_query_count"]),
            answerable_query_count=int(payload["answerable_query_count"]),
            unanswerable_query_count=int(payload["unanswerable_query_count"]),
            relevant_query_count=int(payload["relevant_query_count"]),
            query_with_results_count=int(payload["query_with_results_count"]),
            query_without_results_count=int(payload["query_without_results_count"]),
            hit_at_k=float(payload["hit_at_k"]),
            recall_at_k=float(payload["recall_at_k"]),
            mrr=float(payload["mrr"]),
            average_latency_ms=float(payload["average_latency_ms"]),
            p50_latency_ms=float(payload["p50_latency_ms"]),
            p95_latency_ms=float(payload["p95_latency_ms"]),
            max_latency_ms=float(payload["max_latency_ms"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluationRetriever(Protocol):
    name: str
    retriever_type: str
    config: dict[str, Any]

    def retrieve(self, entry: DevQAEntry, *, top_k: int) -> list[RetrievalHit]:
        """Return ranked retrieval hits for one dev-QA entry."""


def repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[3]


def build_retrieval_run_id(
    *,
    metadata: DevQAMetadata,
    retriever_name: str,
    retriever_type: str,
    top_k: int,
) -> str:
    if top_k <= 0:
        raise ValueError("top_k must be > 0")

    parts = [
        metadata.snapshot_id,
        metadata.dataset_version,
        _slugify(retriever_type),
        _slugify(retriever_name),
        f"top{top_k}",
    ]
    return "-".join(part for part in parts if part)


def default_retrieval_run_paths(
    *,
    metadata: DevQAMetadata,
    retriever_name: str,
    retriever_type: str,
    top_k: int,
    repo_root: Path | None = None,
    runs_dir: Path = DEFAULT_RUNS_DIR,
) -> tuple[Path, Path]:
    run_id = build_retrieval_run_id(
        metadata=metadata,
        retriever_name=retriever_name,
        retriever_type=retriever_type,
        top_k=top_k,
    )
    root = repo_root or repo_root_from_module()
    output_dir = root / runs_dir
    return (
        output_dir / f"{run_id}{RESULTS_FILENAME_SUFFIX}",
        output_dir / f"{run_id}{SUMMARY_FILENAME_SUFFIX}",
    )


def evaluate_retriever(
    *,
    retriever: EvaluationRetriever,
    entries: Iterable[DevQAEntry],
    metadata: DevQAMetadata,
    registry: EvidenceRegistry,
    top_k: int = DEFAULT_EVAL_TOP_K,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> tuple[list[QueryRetrievalResult], RetrievalRunSummary]:
    if top_k <= 0:
        raise ValueError("top_k must be > 0")

    entries = list(entries)
    validate_dev_qa_dataset(entries=entries, metadata=metadata, registry=registry)

    run_id = build_retrieval_run_id(
        metadata=metadata,
        retriever_name=retriever.name,
        retriever_type=retriever.retriever_type,
        top_k=top_k,
    )

    results: list[QueryRetrievalResult] = []
    for entry in entries:
        start_ns = int(clock_ns())
        raw_hits = retriever.retrieve(entry, top_k=top_k)
        end_ns = int(clock_ns())
        normalized_hits = canonicalize_hits(raw_hits, top_k=top_k)
        relevant_kind, relevant_ids = _relevant_identifiers(entry)
        matched_ids, reciprocal_rank = _match_hits(normalized_hits, relevant_kind, relevant_ids)
        recall = (len(matched_ids) / len(relevant_ids)) if relevant_ids else 0.0
        latency_ms = max(0.0, (end_ns - start_ns) / 1_000_000.0)

        results.append(
            QueryRetrievalResult(
                artifact_version=EVAL_ARTIFACT_VERSION,
                run_id=run_id,
                dataset_name=metadata.dataset_name,
                dataset_version=metadata.dataset_version,
                snapshot_id=metadata.snapshot_id,
                retriever_name=retriever.name,
                retriever_type=retriever.retriever_type,
                retriever_config=_normalize_json_value(retriever.config),
                query_id=entry.query_id,
                question=entry.question,
                answerable=entry.answerable,
                category=entry.category,
                tags=list(entry.tags),
                top_k=top_k,
                latency_ms=round(latency_ms, 6),
                relevant_identifier_kind=relevant_kind,
                relevant_identifier_count=len(relevant_ids),
                matched_relevant_count=len(matched_ids),
                hit=bool(matched_ids),
                reciprocal_rank=round(reciprocal_rank, 6),
                recall=round(recall, 6),
                expected_chunk_ids=list(entry.expected_chunk_ids),
                expected_section_ids=list(entry.expected_section_ids),
                hits=normalized_hits,
            )
        )

    summary = summarize_retrieval_results(results)
    return results, summary


def evaluate_default_dev_qa_dataset(
    *,
    retriever: EvaluationRetriever,
    top_k: int = DEFAULT_EVAL_TOP_K,
    dataset_path: Path | None = None,
    metadata_path: Path | None = None,
    registry_path: Path | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> tuple[list[QueryRetrievalResult], RetrievalRunSummary]:
    default_dataset_path, default_metadata_path, default_registry_path = default_dev_qa_paths()
    resolved_dataset_path = dataset_path or default_dataset_path
    resolved_metadata_path = metadata_path or default_metadata_path
    resolved_registry_path = registry_path or default_registry_path

    entries = (
        load_default_dev_qa_dataset()
        if resolved_dataset_path == default_dataset_path and dataset_path is None
        else load_dev_qa_dataset(resolved_dataset_path)
    )
    metadata = (
        load_default_dev_qa_metadata()
        if resolved_metadata_path == default_metadata_path and metadata_path is None
        else load_dev_qa_metadata(resolved_metadata_path)
    )
    registry = (
        load_default_evidence_registry()
        if resolved_registry_path == default_registry_path and registry_path is None
        else load_evidence_registry(resolved_registry_path)
    )
    return evaluate_retriever(
        retriever=retriever,
        entries=entries,
        metadata=metadata,
        registry=registry,
        top_k=top_k,
        clock_ns=clock_ns,
    )


def summarize_retrieval_results(results: Iterable[QueryRetrievalResult]) -> RetrievalRunSummary:
    result_rows = list(results)
    if not result_rows:
        raise ValueError("Cannot summarize an empty retrieval run")

    first = result_rows[0]
    answerable_rows = [row for row in result_rows if row.answerable]
    relevant_rows = [row for row in result_rows if row.relevant_identifier_count > 0]
    latency_values = [row.latency_ms for row in result_rows]

    hit_at_k = _mean([1.0 if row.hit else 0.0 for row in relevant_rows])
    recall_at_k = _mean([row.recall for row in relevant_rows])
    mrr = _mean([row.reciprocal_rank for row in relevant_rows])

    return RetrievalRunSummary(
        artifact_version=EVAL_ARTIFACT_VERSION,
        run_id=first.run_id,
        dataset_name=first.dataset_name,
        dataset_version=first.dataset_version,
        snapshot_id=first.snapshot_id,
        retriever_name=first.retriever_name,
        retriever_type=first.retriever_type,
        retriever_config=dict(first.retriever_config),
        top_k=first.top_k,
        total_query_count=len(result_rows),
        answerable_query_count=len(answerable_rows),
        unanswerable_query_count=len(result_rows) - len(answerable_rows),
        relevant_query_count=len(relevant_rows),
        query_with_results_count=sum(1 for row in result_rows if row.hits),
        query_without_results_count=sum(1 for row in result_rows if not row.hits),
        hit_at_k=round(hit_at_k, 6),
        recall_at_k=round(recall_at_k, 6),
        mrr=round(mrr, 6),
        average_latency_ms=round(_mean(latency_values), 6),
        p50_latency_ms=round(_percentile(latency_values, 0.50), 6),
        p95_latency_ms=round(_percentile(latency_values, 0.95), 6),
        max_latency_ms=round(max(latency_values), 6),
    )


def write_query_results(path: Path, results: Iterable[QueryRetrievalResult]) -> int:
    return write_jsonl(path, [result.to_dict() for result in results])


def load_query_results(path: Path) -> list[QueryRetrievalResult]:
    return [QueryRetrievalResult.from_dict(payload) for payload in read_jsonl(path)]


def write_retrieval_run_summary(path: Path, summary: RetrievalRunSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_retrieval_run_summary(path: Path) -> RetrievalRunSummary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid summary payload in {path}: expected object")
    return RetrievalRunSummary.from_dict(payload)


def render_retrieval_evaluation_report(
    summary: RetrievalRunSummary,
    *,
    results_path: Path,
    summary_path: Path,
) -> str:
    lines = [
        "Retrieval evaluation completed",
        f"run_id: {summary.run_id}",
        f"dataset: {summary.dataset_name} ({summary.snapshot_id} / {summary.dataset_version})",
        f"retriever: {summary.retriever_name} [{summary.retriever_type}]",
        f"top_k: {summary.top_k}",
        (
            "queries: total="
            f"{summary.total_query_count}, answerable={summary.answerable_query_count}, "
            f"unanswerable={summary.unanswerable_query_count}"
        ),
        (
            "metrics: hit@k="
            f"{summary.hit_at_k:.6f}, recall@k={summary.recall_at_k:.6f}, mrr={summary.mrr:.6f}"
        ),
        (
            "latency_ms: avg="
            f"{summary.average_latency_ms:.3f}, p50={summary.p50_latency_ms:.3f}, "
            f"p95={summary.p95_latency_ms:.3f}, max={summary.max_latency_ms:.3f}"
        ),
        f"results: {results_path}",
        f"summary: {summary_path}",
    ]
    return "\n".join(lines)


def canonicalize_hits(hits: Iterable[RetrievalHit], *, top_k: int) -> list[RetrievalHit]:
    if top_k <= 0:
        raise ValueError("top_k must be > 0")

    normalized_hits = list(hits)
    if not normalized_hits:
        return []

    sorted_hits = sorted(
        enumerate(normalized_hits),
        key=lambda item: _hit_sort_key(hit=item[1], ordinal=item[0]),
    )

    unique_hits: list[RetrievalHit] = []
    seen_chunk_ids: set[str] = set()
    for _, hit in sorted_hits:
        chunk_id = str(hit.chunk_id).strip()
        if not chunk_id:
            raise ValueError("Retrieval hits must include a non-empty chunk_id")
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        unique_hits.append(
            RetrievalHit(
                chunk_id=chunk_id,
                score=float(hit.score),
                rank=len(unique_hits) + 1,
                doc_id=(str(hit.doc_id) if hit.doc_id is not None else None),
                section_id=(str(hit.section_id) if hit.section_id is not None else None),
                metadata=_normalize_json_value(hit.metadata),
            )
        )
        if len(unique_hits) >= top_k:
            break
    return unique_hits


def _relevant_identifiers(entry: DevQAEntry) -> tuple[str | None, set[str]]:
    if entry.expected_chunk_ids:
        return "chunk_id", set(entry.expected_chunk_ids)
    if entry.expected_section_ids:
        return "section_id", set(entry.expected_section_ids)
    return None, set()


def _match_hits(
    hits: Iterable[RetrievalHit],
    relevant_identifier_kind: str | None,
    relevant_identifiers: set[str],
) -> tuple[set[str], float]:
    if not relevant_identifier_kind or not relevant_identifiers:
        return set(), 0.0

    matched: set[str] = set()
    reciprocal_rank = 0.0
    for hit in hits:
        identifier = _hit_identifier(hit, relevant_identifier_kind)
        if identifier in relevant_identifiers:
            matched.add(identifier)
            if reciprocal_rank == 0.0:
                reciprocal_rank = 1.0 / float(hit.rank)
    return matched, reciprocal_rank


def _hit_identifier(hit: RetrievalHit, relevant_identifier_kind: str) -> str | None:
    if relevant_identifier_kind == "chunk_id":
        return hit.chunk_id
    if relevant_identifier_kind == "section_id":
        return hit.section_id
    raise ValueError(f"Unsupported relevant identifier kind: {relevant_identifier_kind}")


def _hit_sort_key(*, hit: RetrievalHit, ordinal: int) -> tuple[int, float, str, int]:
    rank = hit.rank if hit.rank > 0 else ordinal + 1
    return (int(rank), -float(hit.score), str(hit.chunk_id), ordinal)


def _slugify(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "retriever"


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _percentile(values: Iterable[float], percentile: float) -> float:
    values = sorted(float(value) for value in values)
    if not values:
        return 0.0
    if percentile <= 0:
        return values[0]
    if percentile >= 1:
        return values[-1]
    index = math.ceil(percentile * len(values)) - 1
    index = max(0, min(index, len(values) - 1))
    return values[index]
