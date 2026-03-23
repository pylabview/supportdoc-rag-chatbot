from __future__ import annotations

from types import MappingProxyType

from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode, RefusalRecord

from .citation_validator import CitationValidationResult
from .policy_types import RetrievalSufficiencyDecision

CANONICAL_REFUSAL_MESSAGES = MappingProxyType(
    {
        RefusalReasonCode.INSUFFICIENT_EVIDENCE: (
            "I can’t answer that confidently from the approved support corpus."
        ),
        RefusalReasonCode.NO_RELEVANT_DOCS: (
            "I can’t answer that from the approved support corpus."
        ),
        RefusalReasonCode.CITATION_VALIDATION_FAILED: (
            "I can’t provide a supported answer because the citations could not be validated."
        ),
        RefusalReasonCode.OUT_OF_SCOPE: (
            "I can’t answer that because it is outside the approved support corpus."
        ),
    }
)


def build_refusal_response(
    reason_code: RefusalReasonCode | str,
    *,
    next_step: str | None = None,
) -> QueryResponse:
    """Build a canonical structured refusal response for the given reason code."""

    resolved_reason_code = RefusalReasonCode(reason_code)
    message = render_refusal_message(resolved_reason_code, next_step=next_step)
    return QueryResponse(
        final_answer=message,
        citations=[],
        refusal=RefusalRecord(
            is_refusal=True,
            reason_code=resolved_reason_code,
            message=message,
        ),
    )


def render_refusal_message(
    reason_code: RefusalReasonCode | str,
    *,
    next_step: str | None = None,
) -> str:
    """Render the canonical user-facing refusal message, optionally with next-step guidance."""

    resolved_reason_code = RefusalReasonCode(reason_code)
    message = CANONICAL_REFUSAL_MESSAGES[resolved_reason_code]

    normalized_next_step = _normalize_optional_next_step(next_step)
    if normalized_next_step is None:
        return message

    return f"{message} Next step: {_ensure_terminal_punctuation(normalized_next_step)}"


def build_refusal_from_retrieval_decision(
    decision: RetrievalSufficiencyDecision,
    *,
    next_step: str | None = None,
) -> QueryResponse:
    """Convert a deterministic gating refusal into the canonical structured refusal response."""

    reason_code = map_retrieval_decision_to_reason_code(decision)
    return build_refusal_response(reason_code, next_step=next_step)


def build_refusal_from_citation_validation(
    result: CitationValidationResult,
    *,
    next_step: str | None = None,
) -> QueryResponse:
    """Convert deterministic citation validation failures into the canonical refusal response."""

    reason_code = map_citation_validation_to_reason_code(result)
    return build_refusal_response(reason_code, next_step=next_step)


def map_retrieval_decision_to_reason_code(
    decision: RetrievalSufficiencyDecision,
) -> RefusalReasonCode:
    """Resolve the canonical refusal reason code for a retrieval gating refusal."""

    if decision.refusal_reason_code is None:
        raise ValueError(
            "Retrieval sufficiency decision does not correspond to a refusal reason code"
        )
    return decision.refusal_reason_code


def map_citation_validation_to_reason_code(
    result: CitationValidationResult,
) -> RefusalReasonCode:
    """Resolve the canonical refusal reason code for a citation validation failure."""

    if result.is_valid or not result.failures:
        raise ValueError("Citation validation result must contain failures to build a refusal")
    return RefusalReasonCode.CITATION_VALIDATION_FAILED


def _normalize_optional_next_step(next_step: str | None) -> str | None:
    if next_step is None:
        return None
    normalized = next_step.strip()
    if not normalized:
        raise ValueError("next_step must not be blank")
    return normalized


def _ensure_terminal_punctuation(text: str) -> str:
    if text[-1] in ".!?":
        return text
    return f"{text}."


__all__ = [
    "CANONICAL_REFUSAL_MESSAGES",
    "build_refusal_from_citation_validation",
    "build_refusal_from_retrieval_decision",
    "build_refusal_response",
    "map_citation_validation_to_reason_code",
    "map_retrieval_decision_to_reason_code",
    "render_refusal_message",
]
