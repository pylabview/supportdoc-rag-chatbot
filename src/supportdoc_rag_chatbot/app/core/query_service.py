from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
from supportdoc_rag_chatbot.config import BackendSettings, get_request_settings

from .errors import QueryPipelineConfigurationError, QueryPipelineRuntimeError
from .retrieval import QueryRetriever, create_query_retriever

DEFAULT_QUERY_MAX_GENERATION_ATTEMPTS = 2


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
        retrieved = self.retriever.retrieve(validated_question, top_k=self.top_k)
        decision = evaluate_retrieval_sufficiency(
            _build_sufficiency_request(validated_question, retrieved),
            thresholds=self.thresholds,
        )
        if decision.should_refuse:
            return build_refusal_from_retrieval_decision(decision)

        prompt = build_trust_prompt(
            question=validated_question,
            retrieved_chunks=retrieved.to_prompt_chunks(),
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
                if (
                    result.failure.code is GenerationFailureCode.PARSE_ERROR
                    and attempt < self.max_generation_attempts
                ):
                    continue
                if result.failure.code is GenerationFailureCode.PARSE_ERROR:
                    return build_refusal_response(RefusalReasonCode.CITATION_VALIDATION_FAILED)
                raise QueryPipelineRuntimeError(_render_generation_failure(result.failure))

            response = result.require_response()
            validation = validate_query_response_citations(
                response,
                retrieved_chunks=retrieved.to_citation_contexts(),
            )
            if validation.is_valid:
                return response
            if validation.should_retry and attempt < self.max_generation_attempts:
                continue
            return build_refusal_from_citation_validation(validation)

        return build_refusal_response(RefusalReasonCode.CITATION_VALIDATION_FAILED)


def create_query_orchestrator(*, settings: BackendSettings) -> QueryOrchestrator:
    """Create the canonical backend query orchestrator from backend settings."""

    try:
        retriever = create_query_retriever(mode=settings.query_retrieval_mode)
    except ValueError as exc:
        raise QueryPipelineConfigurationError(
            f"Invalid retrieval backend configuration: {exc}"
        ) from exc

    try:
        generation_client = create_generation_client(
            mode=settings.query_generation_mode,
            base_url=settings.query_generation_base_url,
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
