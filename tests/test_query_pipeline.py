from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import pytest

from supportdoc_rag_chatbot.app.client import (
    FixtureGenerationClient,
    GenerationBackendMode,
    GenerationFailure,
    GenerationFailureCode,
    GenerationRequest,
    GenerationResult,
)
from supportdoc_rag_chatbot.app.core import (
    ArtifactDenseQueryRetriever,
    FixtureQueryRetriever,
    QueryOrchestrator,
    QueryPipelineConfigurationError,
    RetrievedEvidenceChunk,
)
from supportdoc_rag_chatbot.app.schemas import (
    CitationRecord,
    RefusalReasonCode,
    build_example_answer_response,
)
from supportdoc_rag_chatbot.ingestion.jsonl import write_jsonl
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import build_embedding_artifacts
from supportdoc_rag_chatbot.retrieval.indexes import build_faiss_index_artifacts


@dataclass(slots=True)
class SequenceGenerationClient:
    responses: Sequence[GenerationResult]
    backend_mode: GenerationBackendMode = GenerationBackendMode.FIXTURE
    backend_name: str = "sequence-test"
    requests: list[GenerationRequest] = field(default_factory=list)
    _responses: list[GenerationResult] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._responses = list(self.responses)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("SequenceGenerationClient received more calls than expected")
        return self._responses.pop(0)

    def close(self) -> None:
        return None


@dataclass(slots=True)
class FailIfCalledGenerationClient:
    backend_mode: GenerationBackendMode = GenerationBackendMode.FIXTURE
    backend_name: str = "fail-if-called"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError(f"generation should not be called for request {request!r}")

    def close(self) -> None:
        return None


@dataclass(slots=True)
class FakeEmbedder:
    vectors_by_text: dict[str, list[float]]
    model_name: str = "fake-embedder"

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(self.vectors_by_text[text]) for text in texts]


def test_query_orchestrator_returns_supported_answer_with_fixture_retrieval_and_generation() -> (
    None
):
    orchestrator = QueryOrchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=FixtureGenerationClient(),
        top_k=3,
    )

    response = orchestrator.run("What is a Pod?")

    assert response.refusal.is_refusal is False
    assert (
        response.citations[0].chunk_id == "content-en-docs-concepts-workloads-pods-pods__chunk-0001"
    )
    assert response.final_answer.startswith("A Pod is the smallest deployable unit")


def test_query_orchestrator_returns_insufficient_evidence_refusal_without_generation() -> None:
    single_support_chunk = RetrievedEvidenceChunk(
        doc_id="content-en-docs-concepts-workloads-pods-pods",
        chunk_id="content-en-docs-concepts-workloads-pods-pods__chunk-0001",
        text=(
            "A Pod is the smallest deployable unit in Kubernetes and can run one or more "
            "containers that share network and storage resources."
        ),
        score=0.97,
        rank=1,
        start_offset=0,
        end_offset=128,
    )
    orchestrator = QueryOrchestrator(
        retriever=FixtureQueryRetriever(
            hits_by_question={
                "What is a Pod?": (single_support_chunk,),
            }
        ),
        generation_client=FailIfCalledGenerationClient(),
        top_k=3,
    )

    response = orchestrator.run("What is a Pod?")

    assert response.refusal.is_refusal is True
    assert response.refusal.reason_code is RefusalReasonCode.INSUFFICIENT_EVIDENCE
    assert response.citations == []


def test_query_orchestrator_retries_parse_failure_once_then_refuses() -> None:
    parse_failure = GenerationResult.from_failure(
        GenerationFailure(
            code=GenerationFailureCode.PARSE_ERROR,
            message="Generation backend returned malformed JSON.",
            backend_name="sequence-test",
        )
    )
    generation_client = SequenceGenerationClient([parse_failure, parse_failure])
    orchestrator = QueryOrchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=generation_client,
        top_k=3,
    )

    response = orchestrator.run("What is a Pod?")

    assert len(generation_client.requests) == 2
    assert response.refusal.is_refusal is True
    assert response.refusal.reason_code is RefusalReasonCode.CITATION_VALIDATION_FAILED


def test_query_orchestrator_repairs_missing_citation_markers_before_retry() -> None:
    missing_marker_response = build_example_answer_response().model_copy(
        update={
            "final_answer": (
                "A Pod is the smallest deployable unit in Kubernetes and can run one or more "
                "containers that share network and storage resources."
            )
        }
    )
    generation_client = SequenceGenerationClient(
        [GenerationResult.success(missing_marker_response)]
    )
    orchestrator = QueryOrchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=generation_client,
        top_k=3,
    )

    response = orchestrator.run("What is a Pod?")

    assert len(generation_client.requests) == 1
    assert response.refusal.is_refusal is False
    assert response.citations[0].marker == "[1]"
    assert response.final_answer.endswith("resources [1].")


def test_query_orchestrator_retries_non_repairable_citation_invalid_output_once_then_refuses() -> (
    None
):
    invalid_response = build_example_answer_response().model_copy(
        update={
            "final_answer": (
                "A Pod is the smallest deployable unit in Kubernetes and can run one or more "
                "containers that share network and storage resources [99]."
            )
        }
    )
    generation_client = SequenceGenerationClient(
        [
            GenerationResult.success(invalid_response),
            GenerationResult.success(invalid_response),
        ]
    )
    orchestrator = QueryOrchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=generation_client,
        top_k=3,
    )

    response = orchestrator.run("What is a Pod?")

    assert len(generation_client.requests) == 2
    assert response.refusal.is_refusal is True
    assert response.refusal.reason_code is RefusalReasonCode.CITATION_VALIDATION_FAILED


def test_artifact_dense_query_retriever_returns_ranked_chunks_when_artifacts_exist(
    tmp_path: Path,
) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    embedding_metadata_path = tmp_path / "chunk_embeddings.metadata.json"
    vectors_path = tmp_path / "chunk_embeddings.f32"
    index_path = tmp_path / "chunk_index.faiss"
    index_metadata_path = tmp_path / "chunk_index.metadata.json"
    row_mapping_path = tmp_path / "chunk_index.row_mapping.json"
    chunk_one = ChunkRecord(
        snapshot_id="snap-1",
        doc_id="doc-pods",
        chunk_id="doc-pods__chunk-0001",
        section_id="doc-pods__section-0001",
        section_index=0,
        chunk_index=0,
        doc_title="Pods",
        section_path=["Concepts", "Pods"],
        source_path="pods.md",
        source_url="https://example.test/pods",
        license="CC-BY",
        attribution="Kubernetes",
        language="en",
        start_offset=0,
        end_offset=24,
        token_count=4,
        text="Pod basics and lifecycle.",
    )
    chunk_two = ChunkRecord(
        snapshot_id="snap-1",
        doc_id="doc-services",
        chunk_id="doc-services__chunk-0001",
        section_id="doc-services__section-0001",
        section_index=0,
        chunk_index=0,
        doc_title="Services",
        section_path=["Concepts", "Services"],
        source_path="services.md",
        source_url="https://example.test/services",
        license="CC-BY",
        attribution="Kubernetes",
        language="en",
        start_offset=0,
        end_offset=20,
        token_count=3,
        text="Service networking overview.",
    )
    write_jsonl(chunks_path, [chunk_one, chunk_two])
    embedder = FakeEmbedder(
        {
            chunk_one.text: [1.0, 0.0],
            chunk_two.text: [0.0, 1.0],
            "What is a Pod?": [1.0, 0.0],
        }
    )
    build_embedding_artifacts(
        chunks_path=chunks_path,
        vectors_path=vectors_path,
        metadata_path=embedding_metadata_path,
        embedder=embedder,
        batch_size=2,
    )
    build_faiss_index_artifacts(
        embedding_metadata_path=embedding_metadata_path,
        index_path=index_path,
        metadata_path=index_metadata_path,
        row_mapping_path=row_mapping_path,
    )
    retriever = ArtifactDenseQueryRetriever(
        index_path=index_path,
        metadata_path=index_metadata_path,
        row_mapping_path=row_mapping_path,
        embedder=embedder,
    )

    bundle = retriever.retrieve("What is a Pod?", top_k=2)

    assert [chunk.chunk_id for chunk in bundle.chunks] == [
        "doc-pods__chunk-0001",
        "doc-services__chunk-0001",
    ]
    assert bundle.chunks[0].score > bundle.chunks[1].score
    assert bundle.score_normalization.value == "unit_interval"


def test_query_orchestrator_raises_clear_error_when_artifact_retrieval_artifacts_are_missing(
    tmp_path: Path,
) -> None:
    orchestrator = QueryOrchestrator(
        retriever=ArtifactDenseQueryRetriever(
            index_path=tmp_path / "missing.faiss",
            metadata_path=tmp_path / "missing.metadata.json",
            row_mapping_path=tmp_path / "missing.row_mapping.json",
        ),
        generation_client=FixtureGenerationClient(),
        top_k=3,
    )

    with pytest.raises(
        QueryPipelineConfigurationError, match="artifact retrieval metadata not found"
    ):
        orchestrator.run("What is a Pod?")


def test_supported_orchestration_can_validate_custom_artifact_citations() -> None:
    custom_response = build_example_answer_response().model_copy(
        update={
            "citations": [
                CitationRecord(
                    marker="[1]",
                    doc_id="content-en-docs-concepts-workloads-pods-pods",
                    chunk_id="content-en-docs-concepts-workloads-pods-pods__chunk-0001",
                    start_offset=0,
                    end_offset=118,
                )
            ]
        }
    )
    generation_client = SequenceGenerationClient([GenerationResult.success(custom_response)])
    orchestrator = QueryOrchestrator(
        retriever=FixtureQueryRetriever(),
        generation_client=generation_client,
        top_k=3,
    )

    response = orchestrator.run("What is a Pod?")

    assert response.refusal.is_refusal is False
    assert len(generation_client.requests) == 1
