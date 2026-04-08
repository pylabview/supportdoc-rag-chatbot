from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from supportdoc_rag_chatbot.app.core import PgvectorQueryRetriever, QueryPipelineConfigurationError
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_PGVECTOR_DISTANCE_METRIC,
    PgvectorRuntimeMetadata,
    PgvectorSearchMatch,
)


@dataclass(slots=True)
class FakeEmbedder:
    vectors_by_text: dict[str, list[float]]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [list(self.vectors_by_text[text]) for text in texts]


@dataclass(slots=True)
class FakePgvectorBackend:
    matches: list[PgvectorSearchMatch]
    runtime_metadata: PgvectorRuntimeMetadata
    calls: list[tuple[list[float], int]] = field(default_factory=list)

    def search(self, query_vector: list[float], *, top_k: int = 5) -> list[PgvectorSearchMatch]:
        self.calls.append((list(query_vector), top_k))
        return list(self.matches)


def _sample_runtime_metadata() -> PgvectorRuntimeMetadata:
    return PgvectorRuntimeMetadata(
        runtime_id="default",
        artifact_version="v1",
        snapshot_id="snapshot-001",
        embedding_model_name="demo-model",
        vector_dimension=2,
        row_count=1,
        source_chunks_path="data/processed/chunks.jsonl",
        embedding_metadata_path="data/processed/embeddings/chunk_embeddings.metadata.json",
        vectors_path="data/processed/embeddings/chunk_embeddings.f32",
        distance_metric=DEFAULT_PGVECTOR_DISTANCE_METRIC,
    )


def _sample_chunk() -> ChunkRecord:
    return ChunkRecord(
        snapshot_id="snapshot-001",
        doc_id="doc-001",
        chunk_id="doc-001__chunk-0001",
        section_id="section-001",
        section_index=0,
        chunk_index=0,
        doc_title="Pods",
        section_path=["Concepts", "Workloads", "Pods"],
        source_path="content/en/docs/concepts/workloads/pods/pods.md",
        source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
        license="CC BY 4.0",
        attribution="Kubernetes Docs",
        language="en",
        start_offset=0,
        end_offset=42,
        token_count=8,
        text="A Pod is the smallest deployable unit.",
    )


def test_pgvector_query_retriever_normalizes_matches_into_existing_evidence_bundle() -> None:
    backend = FakePgvectorBackend(
        matches=[PgvectorSearchMatch(chunk=_sample_chunk(), raw_score=0.5)],
        runtime_metadata=_sample_runtime_metadata(),
    )
    retriever = PgvectorQueryRetriever(
        dsn="postgresql://demo:demo@localhost:5432/supportdoc",
        backend=backend,
        embedder=FakeEmbedder({"What is a Pod?": [0.1, 0.2]}),
    )

    bundle = retriever.retrieve("What is a Pod?", top_k=1)

    assert backend.calls == [([0.1, 0.2], 1)]
    assert bundle.retriever_name == "pgvector-retriever"
    assert bundle.retriever_type == "pgvector"
    assert bundle.config["dsn_configured"] is True
    assert bundle.config["distance_metric"] == DEFAULT_PGVECTOR_DISTANCE_METRIC
    assert bundle.chunks[0].chunk_id == "doc-001__chunk-0001"
    assert bundle.chunks[0].score == pytest.approx(0.75)
    assert bundle.chunks[0].metadata == {"raw_score": 0.5}


def test_pgvector_query_retriever_requires_fixture_path_when_fixture_embedder_mode_is_selected() -> (
    None
):
    retriever = PgvectorQueryRetriever(
        dsn="postgresql://demo:demo@localhost:5432/supportdoc",
        backend=FakePgvectorBackend(matches=[], runtime_metadata=_sample_runtime_metadata()),
        embedder_mode="fixture",
    )

    with pytest.raises(QueryPipelineConfigurationError, match="embedder fixture path"):
        retriever.retrieve("What is a Pod?", top_k=1)
