from __future__ import annotations

from supportdoc_rag_chatbot.app.schemas import CitationRecord, QueryResponse, RefusalRecord
from supportdoc_rag_chatbot.app.services import (
    CitationValidationFailureCode,
    CitationValidationOutcome,
    RetrievedChunkCitationContext,
    validate_query_response_citations,
)
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord


def make_retrieved_chunk(
    *,
    doc_id: str = "doc-pods",
    chunk_id: str = "chunk-pods-001",
    text: str = "A Pod is the smallest deployable unit in Kubernetes.",
    start_offset: int = 0,
) -> RetrievedChunkCitationContext:
    return RetrievedChunkCitationContext(
        doc_id=doc_id,
        chunk_id=chunk_id,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        text=text,
    )


def make_chunk_record(
    *,
    doc_id: str = "doc-pods",
    chunk_id: str = "chunk-pods-001",
    text: str = "A Pod is the smallest deployable unit in Kubernetes.",
) -> ChunkRecord:
    return ChunkRecord(
        snapshot_id="k8s-9e1e32b",
        doc_id=doc_id,
        chunk_id=chunk_id,
        section_id=f"section-{chunk_id}",
        section_index=0,
        chunk_index=0,
        doc_title="Pods",
        section_path=["Pods"],
        source_path="content/en/docs/concepts/workloads/pods/pods.md",
        source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
        license="CC BY 4.0",
        attribution="Kubernetes Documentation © The Kubernetes Authors",
        language="en",
        start_offset=0,
        end_offset=len(text),
        token_count=len(text.split()),
        text=text,
    )


def make_supported_response(
    *,
    final_answer: str,
    citations: list[CitationRecord],
) -> QueryResponse:
    return QueryResponse(
        final_answer=final_answer,
        citations=citations,
        refusal=RefusalRecord(
            is_refusal=False,
            reason_code=None,
            message=None,
        ),
    )


def test_validate_query_response_citations_accepts_supported_answer() -> None:
    response = make_supported_response(
        final_answer=(
            "A Pod is the smallest deployable unit in Kubernetes [1]. "
            "A Service provides stable networking for a set of Pods [2]."
        ),
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=40,
            ),
            CitationRecord(
                marker="[2]",
                doc_id="doc-service",
                chunk_id="chunk-service-002",
                start_offset=0,
                end_offset=45,
            ),
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[
            make_retrieved_chunk(
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                text="A Pod is the smallest deployable unit in Kubernetes.",
            ),
            make_retrieved_chunk(
                doc_id="doc-service",
                chunk_id="chunk-service-002",
                text="A Service provides stable networking for a set of Pods.",
            ),
        ],
    )

    assert result.outcome is CitationValidationOutcome.VALID
    assert result.failures == ()


def test_validate_query_response_citations_accepts_chunk_record_instances() -> None:
    response = make_supported_response(
        final_answer="A Pod is the smallest deployable unit in Kubernetes [1].",
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=40,
            )
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_chunk_record()],
    )

    assert result.is_valid is True


def test_validate_query_response_citations_detects_missing_sentence_citation() -> None:
    response = make_supported_response(
        final_answer=(
            "A Pod is the smallest deployable unit in Kubernetes [1]. "
            "A Service provides stable networking for a set of Pods."
        ),
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=40,
            )
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_retrieved_chunk()],
    )

    assert result.outcome is CitationValidationOutcome.RETRY
    assert any(
        failure.code is CitationValidationFailureCode.MISSING_CITATION_COVERAGE
        for failure in result.failures
    )


def test_validate_query_response_citations_detects_malformed_marker() -> None:
    response = make_supported_response(
        final_answer="A Pod is the smallest deployable unit in Kubernetes [one].",
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=40,
            )
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_retrieved_chunk()],
    )

    assert result.outcome is CitationValidationOutcome.RETRY
    assert any(
        failure.code is CitationValidationFailureCode.MALFORMED_CITATION_MARKER
        for failure in result.failures
    )


def test_validate_query_response_citations_detects_unknown_marker() -> None:
    response = make_supported_response(
        final_answer="A Pod is the smallest deployable unit in Kubernetes [2].",
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=40,
            )
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_retrieved_chunk()],
    )

    assert result.outcome is CitationValidationOutcome.RETRY
    assert any(
        failure.code is CitationValidationFailureCode.UNKNOWN_CITATION_MARKER
        for failure in result.failures
    )


def test_validate_query_response_citations_detects_non_retrieved_chunk_id() -> None:
    response = make_supported_response(
        final_answer="A Pod is the smallest deployable unit in Kubernetes [1].",
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-missing",
                start_offset=0,
                end_offset=40,
            )
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_retrieved_chunk()],
    )

    assert result.outcome is CitationValidationOutcome.RETRY
    assert any(
        failure.code is CitationValidationFailureCode.NON_RETRIEVED_CHUNK
        for failure in result.failures
    )


def test_validate_query_response_citations_detects_out_of_range_offsets() -> None:
    response = make_supported_response(
        final_answer="A Pod is the smallest deployable unit in Kubernetes [1].",
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=999,
            )
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_retrieved_chunk()],
    )

    assert result.outcome is CitationValidationOutcome.RETRY
    assert any(
        failure.code is CitationValidationFailureCode.OFFSET_OUT_OF_RANGE
        for failure in result.failures
    )


def test_validate_query_response_citations_detects_duplicate_citation_markers() -> None:
    response = make_supported_response(
        final_answer="A Pod is the smallest deployable unit in Kubernetes [1].",
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=0,
                end_offset=20,
            ),
            CitationRecord(
                marker="[1]",
                doc_id="doc-pods",
                chunk_id="chunk-pods-001",
                start_offset=20,
                end_offset=40,
            ),
        ],
    )

    result = validate_query_response_citations(
        response,
        retrieved_chunks=[make_retrieved_chunk()],
    )

    assert result.outcome is CitationValidationOutcome.RETRY
    assert any(
        failure.code is CitationValidationFailureCode.DUPLICATE_CITATION_MARKER
        for failure in result.failures
    )


def test_validate_query_response_citations_accepts_structured_refusal() -> None:
    response = QueryResponse(
        final_answer="I can’t answer that from the approved support corpus.",
        citations=[],
        refusal=RefusalRecord(
            is_refusal=True,
            reason_code="no_relevant_docs",
            message="I can’t answer that from the approved support corpus.",
        ),
    )

    result = validate_query_response_citations(response, retrieved_chunks=[])

    assert result.outcome is CitationValidationOutcome.VALID
    assert result.failures == ()


def test_validate_query_response_citations_refuses_answer_refusal_contradiction() -> None:
    response = QueryResponse(
        final_answer="Pods are the smallest deployable unit in Kubernetes.",
        citations=[],
        refusal=RefusalRecord(
            is_refusal=True,
            reason_code="citation_validation_failed",
            message="Pods are the smallest deployable unit in Kubernetes.",
        ),
    )

    result = validate_query_response_citations(response, retrieved_chunks=[])

    assert result.outcome is CitationValidationOutcome.REFUSE
    assert any(
        failure.code is CitationValidationFailureCode.REFUSAL_ANSWER_CONTRADICTION
        for failure in result.failures
    )
