from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Request

from supportdoc_rag_chatbot.app.client import (
    GenerationClient,
    GenerationFailureCode,
    GenerationRequest,
    create_generation_client,
)
from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode
from supportdoc_rag_chatbot.app.services import (
    RetrievalSufficiencyThresholds,
    build_refusal_from_citation_validation,
    build_refusal_from_retrieval_decision,
    build_refusal_response,
    build_trust_prompt,
    evaluate_retrieval_sufficiency,
    load_retrieval_sufficiency_thresholds,
    validate_query_response_citations,
)
from supportdoc_rag_chatbot.app.services.citation_validator import (
    CitationValidationFailureCode,
    CitationValidationResult,
    extract_citation_markers,
)
from supportdoc_rag_chatbot.app.services.sentence_splitter import split_answer_claims
from supportdoc_rag_chatbot.logging_conf import log_event

if TYPE_CHECKING:
    from supportdoc_rag_chatbot.config import BackendSettings

from .errors import QueryPipelineConfigurationError, QueryPipelineRuntimeError
from .retrieval import QueryRetriever, RetrievalBackendMode, create_query_retriever

DEFAULT_QUERY_MAX_GENERATION_ATTEMPTS = 2

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QueryOrchestrator:
    """Canonical backend orchestration service behind POST /query."""

    retriever: QueryRetriever
    generation_client: GenerationClient
    thresholds: RetrievalSufficiencyThresholds = field(
        default_factory=load_retrieval_sufficiency_thresholds
    )
    top_k: int = 3
    max_generation_attempts: int = DEFAULT_QUERY_MAX_GENERATION_ATTEMPTS

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self.max_generation_attempts <= 0:
            raise ValueError("max_generation_attempts must be > 0")

    def run(self, question: str) -> QueryResponse:
        validated_question = _validate_required_string(question, field_name="question")
        log_event(
            logger,
            "query.orchestration.started",
            retrieval_mode=self.retriever.backend_mode.value,
            retriever_name=self.retriever.name,
            retriever_type=self.retriever.retriever_type,
            generation_mode=self.generation_client.backend_mode.value,
            generation_backend=self.generation_client.backend_name,
            top_k=self.top_k,
            max_generation_attempts=self.max_generation_attempts,
        )

        retrieved = self.retriever.retrieve(validated_question, top_k=self.top_k)
        log_event(
            logger,
            "query.retrieval.completed",
            retrieval_mode=self.retriever.backend_mode.value,
            retriever_name=retrieved.retriever_name,
            retriever_type=retrieved.retriever_type,
            top_k=self.top_k,
            retrieved_count=len(retrieved.chunks),
            top_score=(retrieved.chunks[0].score if retrieved.chunks else None),
        )

        decision = evaluate_retrieval_sufficiency(
            _build_sufficiency_request(validated_question, retrieved),
            thresholds=self.thresholds,
        )
        log_event(
            logger,
            "query.sufficiency.decided",
            retrieval_mode=self.retriever.backend_mode.value,
            sufficiency_action=decision.action.value,
            refusal_reason=(
                decision.refusal_reason_code.value
                if decision.refusal_reason_code is not None
                else None
            ),
            max_answer_sentences=decision.max_answer_sentences,
            available_hit_count=decision.diagnostics.summary.available_hit_count,
            support_count=decision.diagnostics.summary.support_count,
        )
        if decision.should_refuse:
            response = build_refusal_from_retrieval_decision(decision)
            log_event(
                logger,
                "query.refusal.returned",
                stage="retrieval_sufficiency",
                refusal_reason=response.refusal.reason_code.value,
                retry_count=0,
            )
            log_event(
                logger,
                "query.completed",
                outcome="refusal",
                refusal_reason=response.refusal.reason_code.value,
                retry_count=0,
            )
            return response

        prompt = build_trust_prompt(
            question=validated_question,
            retrieved_chunks=retrieved.to_prompt_chunks(),
        )
        log_event(
            logger,
            "query.prompt.rendered",
            retrieved_chunk_count=len(retrieved.chunks),
            max_answer_sentences=decision.max_answer_sentences,
        )
        return self._run_generation_loop(
            question=validated_question,
            retrieved=retrieved,
            prompt=prompt,
            max_answer_sentences=decision.max_answer_sentences,
        )

    def close(self) -> None:
        self.generation_client.close()

    def _run_generation_loop(
        self,
        *,
        question: str,
        retrieved,
        prompt,
        max_answer_sentences: int | None,
    ) -> QueryResponse:
        for attempt in range(1, self.max_generation_attempts + 1):
            log_event(
                logger,
                "query.generation.attempted",
                attempt=attempt,
                generation_mode=self.generation_client.backend_mode.value,
                generation_backend=self.generation_client.backend_name,
                retriever_name=retrieved.retriever_name,
                retriever_type=retrieved.retriever_type,
                retrieved_chunk_count=len(retrieved.chunks),
            )
            result = self.generation_client.generate(
                GenerationRequest(
                    question=question,
                    system_prompt=prompt.system_prompt,
                    user_prompt=prompt.user_prompt,
                    metadata={
                        "attempt": attempt,
                        "retriever_name": retrieved.retriever_name,
                        "retriever_type": retrieved.retriever_type,
                        "retrieved_chunk_ids": [chunk.chunk_id for chunk in retrieved.chunks],
                        "max_answer_sentences": max_answer_sentences,
                    },
                )
            )
            if result.is_failure:
                assert result.failure is not None
                log_event(
                    logger,
                    "query.generation.failed",
                    attempt=attempt,
                    generation_mode=self.generation_client.backend_mode.value,
                    generation_backend=result.failure.backend_name,
                    failure_code=result.failure.code.value,
                    retryable=result.failure.retryable,
                    status_code=result.failure.status_code,
                )
                if (
                    result.failure.code is GenerationFailureCode.PARSE_ERROR
                    and attempt < self.max_generation_attempts
                ):
                    log_event(
                        logger,
                        "query.generation.retry_scheduled",
                        attempt=attempt,
                        retry_count=attempt,
                        retry_reason=result.failure.code.value,
                    )
                    continue
                if result.failure.code is GenerationFailureCode.PARSE_ERROR:
                    response = build_refusal_response(RefusalReasonCode.CITATION_VALIDATION_FAILED)
                    log_event(
                        logger,
                        "query.refusal.returned",
                        stage="generation",
                        refusal_reason=response.refusal.reason_code.value,
                        retry_count=attempt - 1,
                        failure_code=result.failure.code.value,
                    )
                    log_event(
                        logger,
                        "query.completed",
                        outcome="refusal",
                        refusal_reason=response.refusal.reason_code.value,
                        retry_count=attempt - 1,
                    )
                    return response
                raise QueryPipelineRuntimeError(_render_generation_failure(result.failure))

            response = result.require_response()
            validation = validate_query_response_citations(
                response,
                retrieved_chunks=retrieved.to_citation_contexts(),
            )
            repaired_response = _repair_missing_citation_coverage(
                response=response,
                validation=validation,
            )
            if repaired_response is not response:
                response = repaired_response
                validation = validate_query_response_citations(
                    response,
                    retrieved_chunks=retrieved.to_citation_contexts(),
                )
                log_event(
                    logger,
                    "query.citation_validation.repaired",
                    attempt=attempt,
                    citation_validation_outcome=validation.outcome.value,
                    failure_count=len(validation.failures),
                    failure_codes=[failure.code.value for failure in validation.failures],
                )
            log_event(
                logger,
                "query.citation_validation.completed",
                attempt=attempt,
                citation_validation_outcome=validation.outcome.value,
                failure_count=len(validation.failures),
                failure_codes=[failure.code.value for failure in validation.failures],
            )
            if validation.is_valid:
                log_event(
                    logger,
                    "query.completed",
                    outcome="answer",
                    citation_count=len(response.citations),
                    retry_count=attempt - 1,
                )
                return response
            if validation.should_retry and attempt < self.max_generation_attempts:
                log_event(
                    logger,
                    "query.generation.retry_scheduled",
                    attempt=attempt,
                    retry_count=attempt,
                    retry_reason="citation_validation_failed",
                )
                continue
            response = build_refusal_from_citation_validation(validation)
            log_event(
                logger,
                "query.refusal.returned",
                stage="citation_validation",
                refusal_reason=response.refusal.reason_code.value,
                citation_validation_outcome=validation.outcome.value,
                failure_count=len(validation.failures),
                failure_codes=[failure.code.value for failure in validation.failures],
                retry_count=attempt - 1,
            )
            log_event(
                logger,
                "query.completed",
                outcome="refusal",
                refusal_reason=response.refusal.reason_code.value,
                retry_count=attempt - 1,
            )
            return response

        response = build_refusal_response(RefusalReasonCode.CITATION_VALIDATION_FAILED)
        log_event(
            logger,
            "query.refusal.returned",
            stage="generation",
            refusal_reason=response.refusal.reason_code.value,
            retry_count=self.max_generation_attempts - 1,
        )
        log_event(
            logger,
            "query.completed",
            outcome="refusal",
            refusal_reason=response.refusal.reason_code.value,
            retry_count=self.max_generation_attempts - 1,
        )
        return response


def create_query_orchestrator(*, settings: BackendSettings) -> QueryOrchestrator:
    """Create the canonical backend query orchestrator from backend settings."""

    retriever_kwargs: dict[str, Any] = {}
    if settings.query_retrieval_mode is RetrievalBackendMode.ARTIFACT:
        retriever_kwargs = {
            "chunks_path": _optional_path(settings.query_artifact_chunks_path),
            "index_path": _optional_path(settings.query_artifact_index_path),
            "metadata_path": _optional_path(settings.query_artifact_index_metadata_path),
            "row_mapping_path": _optional_path(settings.query_artifact_row_mapping_path),
            "embedder_mode": settings.query_artifact_embedder_mode,
            "embedder_fixture_path": _optional_path(settings.query_artifact_embedder_fixture_path),
        }
    elif settings.query_retrieval_mode is RetrievalBackendMode.PGVECTOR:
        retriever_kwargs = {
            "dsn": settings.query_pgvector_dsn,
            "schema_name": settings.query_pgvector_schema_name,
            "runtime_id": settings.query_pgvector_runtime_id,
            "embedder_mode": settings.query_pgvector_embedder_mode,
            "embedder_fixture_path": _optional_path(settings.query_pgvector_embedder_fixture_path),
        }

    try:
        retriever = create_query_retriever(mode=settings.query_retrieval_mode, **retriever_kwargs)
    except ValueError as exc:
        raise QueryPipelineConfigurationError(
            f"Invalid retrieval backend configuration: {exc}"
        ) from exc

    try:
        generation_client = create_generation_client(
            mode=settings.query_generation_mode,
            base_url=settings.query_generation_base_url,
            model=settings.query_generation_model,
            api_key=settings.query_generation_api_key,
            timeout_seconds=settings.query_generation_timeout_seconds,
        )
    except ValueError as exc:
        raise QueryPipelineConfigurationError(
            f"Invalid generation backend configuration: {exc}"
        ) from exc

    return QueryOrchestrator(
        retriever=retriever,
        generation_client=generation_client,
        top_k=settings.query_top_k,
    )


def get_request_query_orchestrator(request: Request) -> QueryOrchestrator:
    """Resolve and cache the request-scoped query orchestrator on app state."""

    from supportdoc_rag_chatbot.config import get_request_settings

    cached = getattr(request.app.state, "query_orchestrator", None)
    if isinstance(cached, QueryOrchestrator):
        return cached

    settings = get_request_settings(request)
    orchestrator = create_query_orchestrator(settings=settings)
    request.app.state.query_orchestrator = orchestrator
    return orchestrator


def close_cached_query_orchestrator(app: Any) -> None:
    """Close and clear any cached query orchestrator stored on app state."""

    cached = getattr(app.state, "query_orchestrator", None)
    if isinstance(cached, QueryOrchestrator):
        cached.close()
        delattr(app.state, "query_orchestrator")


def _repair_missing_citation_coverage(
    *,
    response: QueryResponse,
    validation: CitationValidationResult,
) -> QueryResponse:
    """Append existing citation markers to uncited claims when markers were omitted.

    This tactical repair handles small models that return valid citation records
    but forget to include the matching marker in final_answer. The normal
    validator still re-validates chunk IDs and offsets after this repair.
    """

    if response.refusal.is_refusal or not response.citations:
        return response
    if not validation.failures:
        return response
    if any(
        failure.code is not CitationValidationFailureCode.MISSING_CITATION_COVERAGE
        for failure in validation.failures
    ):
        return response

    default_marker = response.citations[0].marker
    answer = response.final_answer
    replacements: list[tuple[int, int, str]] = []

    for claim in split_answer_claims(answer):
        if extract_citation_markers(claim.text):
            continue
        replacements.append(
            (
                claim.start_offset,
                claim.end_offset,
                _append_marker_to_claim(claim.text, default_marker),
            )
        )

    if not replacements:
        return response

    repaired_answer = answer
    for start_offset, end_offset, replacement in reversed(replacements):
        repaired_answer = (
            repaired_answer[:start_offset] + replacement + repaired_answer[end_offset:]
        )

    return response.model_copy(update={"final_answer": repaired_answer})


def _append_marker_to_claim(claim_text: str, marker: str) -> str:
    stripped = claim_text.rstrip()
    trailing_whitespace = claim_text[len(stripped) :]
    if stripped.endswith((".", "!", "?")):
        return f"{stripped[:-1].rstrip()} {marker}{stripped[-1]}{trailing_whitespace}"
    return f"{stripped} {marker}{trailing_whitespace}"


def _build_sufficiency_request(question: str, retrieved) -> Any:
    from supportdoc_rag_chatbot.app.services import RetrievalSufficiencyRequest

    return RetrievalSufficiencyRequest.from_retrieval_hits(
        retrieved.to_retrieval_hits(),
        score_normalization=retrieved.score_normalization,
        retriever_name=retrieved.retriever_name,
        retriever_type=retrieved.retriever_type,
        metadata={
            "question": question,
            "retriever_config": dict(retrieved.config),
        },
    )


def _render_generation_failure(failure) -> str:
    return (
        f"Generation backend failed with {failure.code.value}: {failure.message} "
        f"(backend={failure.backend_name})"
    )


def _optional_path(value: str | None) -> Path | None:
    if value is None:
        return None
    return Path(value)


def _validate_required_string(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


__all__ = [
    "DEFAULT_QUERY_MAX_GENERATION_ATTEMPTS",
    "QueryOrchestrator",
    "close_cached_query_orchestrator",
    "create_query_orchestrator",
    "get_request_query_orchestrator",
]
