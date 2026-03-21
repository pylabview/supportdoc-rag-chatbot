from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .artifacts import RetrievalQueryArtifact


@dataclass(slots=True)
class RetrievalMetrics:
    query_count: int
    answerable_query_count: int
    hit_at_k: float
    recall_at_k: float
    mrr: float
    mean_latency_ms: float
    max_latency_ms: float


def compute_retrieval_metrics(results: Iterable[RetrievalQueryArtifact]) -> RetrievalMetrics:
    rows = list(results)
    query_count = len(rows)
    answerable_rows = [row for row in rows if row.answerable]
    answerable_query_count = len(answerable_rows)

    latencies = [max(0.0, float(row.latency_ms)) for row in rows]
    mean_latency_ms = mean(latencies) if latencies else 0.0
    max_latency_ms = max(latencies, default=0.0)

    if answerable_query_count == 0:
        return RetrievalMetrics(
            query_count=query_count,
            answerable_query_count=0,
            hit_at_k=0.0,
            recall_at_k=0.0,
            mrr=0.0,
            mean_latency_ms=mean_latency_ms,
            max_latency_ms=max_latency_ms,
        )

    hit_values: list[float] = []
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []

    for row in answerable_rows:
        relevant = set(row.expected_chunk_ids)
        retrieved = [match.chunk_id for match in row.matches]
        retrieved_relevant = [chunk_id for chunk_id in retrieved if chunk_id in relevant]

        hit_values.append(1.0 if retrieved_relevant else 0.0)
        recall_values.append(len(set(retrieved_relevant)) / len(relevant) if relevant else 0.0)

        reciprocal_rank = 0.0
        for match in row.matches:
            if match.chunk_id in relevant:
                reciprocal_rank = 1.0 / float(match.rank)
                break
        reciprocal_ranks.append(reciprocal_rank)

    return RetrievalMetrics(
        query_count=query_count,
        answerable_query_count=answerable_query_count,
        hit_at_k=mean(hit_values),
        recall_at_k=mean(recall_values),
        mrr=mean(reciprocal_ranks),
        mean_latency_ms=mean_latency_ms,
        max_latency_ms=max_latency_ms,
    )
