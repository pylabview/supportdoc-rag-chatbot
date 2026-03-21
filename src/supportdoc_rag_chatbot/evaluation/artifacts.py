from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_EVALUATION_RUNS_DIR = Path("data/evaluation/runs")


@dataclass(slots=True)
class RetrievedChunkArtifact:
    chunk_id: str
    rank: int
    score: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievedChunkArtifact":
        return cls(
            chunk_id=str(payload["chunk_id"]),
            rank=int(payload["rank"]),
            score=float(payload["score"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RetrievalQueryArtifact:
    query_id: str
    question: str
    answerable: bool
    snapshot_id: str
    retriever_name: str
    top_k: int
    latency_ms: float
    expected_chunk_ids: list[str]
    matches: list[RetrievedChunkArtifact]
    retriever_config: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalQueryArtifact":
        return cls(
            query_id=str(payload["query_id"]),
            question=str(payload["question"]),
            answerable=bool(payload["answerable"]),
            snapshot_id=str(payload["snapshot_id"]),
            retriever_name=str(payload["retriever_name"]),
            top_k=int(payload["top_k"]),
            latency_ms=float(payload["latency_ms"]),
            expected_chunk_ids=[str(item) for item in payload.get("expected_chunk_ids", [])],
            matches=[
                RetrievedChunkArtifact.from_dict(match) for match in payload.get("matches", [])
            ],
            retriever_config=dict(payload.get("retriever_config", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matches"] = [match.to_dict() for match in self.matches]
        return payload


@dataclass(slots=True)
class RetrievalSummaryArtifact:
    run_name: str
    dataset_name: str
    dataset_version: str
    snapshot_id: str
    retriever_name: str
    top_k: int
    query_count: int
    answerable_query_count: int
    hit_at_k: float
    recall_at_k: float
    mrr: float
    mean_latency_ms: float
    max_latency_ms: float
    results_output_path: str
    summary_output_path: str
    retriever_config: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalSummaryArtifact":
        return cls(
            run_name=str(payload["run_name"]),
            dataset_name=str(payload["dataset_name"]),
            dataset_version=str(payload["dataset_version"]),
            snapshot_id=str(payload["snapshot_id"]),
            retriever_name=str(payload["retriever_name"]),
            top_k=int(payload["top_k"]),
            query_count=int(payload["query_count"]),
            answerable_query_count=int(payload["answerable_query_count"]),
            hit_at_k=float(payload["hit_at_k"]),
            recall_at_k=float(payload["recall_at_k"]),
            mrr=float(payload["mrr"]),
            mean_latency_ms=float(payload["mean_latency_ms"]),
            max_latency_ms=float(payload["max_latency_ms"]),
            results_output_path=str(payload["results_output_path"]),
            summary_output_path=str(payload["summary_output_path"]),
            retriever_config=dict(payload.get("retriever_config", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RetrievalRunArtifacts:
    results: list[RetrievalQueryArtifact]
    summary: RetrievalSummaryArtifact


def write_retrieval_results(path: Path, results: Iterable[RetrievalQueryArtifact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")


def read_retrieval_results(path: Path) -> list[RetrievalQueryArtifact]:
    rows: list[RetrievalQueryArtifact] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                row = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} on line {line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"Invalid JSONL record in {path} on line {line_number}: expected object"
                )
            rows.append(RetrievalQueryArtifact.from_dict(row))
    return rows


def write_retrieval_summary(path: Path, summary: RetrievalSummaryArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_retrieval_summary(path: Path) -> RetrievalSummaryArtifact:
    return RetrievalSummaryArtifact.from_dict(json.loads(path.read_text(encoding="utf-8")))
