from __future__ import annotations

import pytest

from supportdoc_rag_chatbot.app.schemas import RefusalReasonCode
from supportdoc_rag_chatbot.app.services import (
    CANONICAL_REFUSAL_MESSAGES,
    CitationValidationFailure,
    CitationValidationFailureCode,
    CitationValidationOutcome,
    CitationValidationResult,
    RetrievalEvidenceHit,
    RetrievalSufficiencyRequest,
    RetrievalSufficiencyThresholds,
    build_refusal_from_citation_validation,
    build_refusal_from_retrieval_decision,
    build_refusal_response,
    evaluate_retrieval_sufficiency,
    map_citation_validation_to_reason_code,
    map_retrieval_decision_to_reason_code,
    render_refusal_message,
)

DEFAULT_THRESHOLDS = RetrievalSufficiencyThresholds(
    k=8,
    T_top1=0.75,
    T_mean3=0.60,
    T_support=0.55,
    N_support=2,
    L_thin_max=3,
    T_nohit=0.20,
)


def make_request(scores: list[float]) -> RetrievalSufficiencyRequest:
    return RetrievalSufficiencyRequest(
        hits=tuple(
            RetrievalEvidenceHit(
                chunk_id=f"chunk-{index}",
                score=score,
                rank=index,
                doc_id=f"doc-{index}",
                section_id=f"section-{index}",
            )
            for index, score in enumerate(scores, start=1)
        ),
    )


@pytest.mark.parametrize(
    ("reason_code", "expected_message"),
    [
        (
            RefusalReasonCode.INSUFFICIENT_EVIDENCE,
            "I can’t answer that confidently from the approved support corpus.",
        ),
        (
            RefusalReasonCode.NO_RELEVANT_DOCS,
            "I can’t answer that from the approved support corpus.",
        ),
        (
            RefusalReasonCode.CITATION_VALIDATION_FAILED,
            "I can’t provide a supported answer because the citations could not be validated.",
        ),
        (
            RefusalReasonCode.OUT_OF_SCOPE,
            "I can’t answer that because it is outside the approved support corpus.",
        ),
    ],
)
def test_build_refusal_response_returns_valid_query_response(
    reason_code: RefusalReasonCode,
    expected_message: str,
) -> None:
    response = build_refusal_response(reason_code)

    assert response.final_answer == expected_message
    assert response.citations == []
    assert response.refusal.is_refusal is True
    assert response.refusal.reason_code is reason_code
    assert response.refusal.message == expected_message


@pytest.mark.parametrize(
    ("reason_code", "expected_message"),
    sorted(CANONICAL_REFUSAL_MESSAGES.items(), key=lambda item: item[0].value),
)
def test_render_refusal_message_matches_canonical_mapping(
    reason_code: RefusalReasonCode,
    expected_message: str,
) -> None:
    assert render_refusal_message(reason_code) == expected_message


def test_render_refusal_message_supports_optional_next_step_guidance() -> None:
    message = render_refusal_message(
        RefusalReasonCode.INSUFFICIENT_EVIDENCE,
        next_step="ask a narrower question about Pods or Services",
    )

    assert message == (
        "I can’t answer that confidently from the approved support corpus. "
        "Next step: ask a narrower question about Pods or Services."
    )


def test_render_refusal_message_rejects_blank_next_step() -> None:
    with pytest.raises(ValueError, match="next_step must not be blank"):
        render_refusal_message(RefusalReasonCode.NO_RELEVANT_DOCS, next_step="   ")


def test_build_refusal_from_retrieval_decision_maps_no_relevant_docs() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.19, 0.10]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    response = build_refusal_from_retrieval_decision(decision)

    assert map_retrieval_decision_to_reason_code(decision) is RefusalReasonCode.NO_RELEVANT_DOCS
    assert response.refusal.reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
    assert response.final_answer == "I can’t answer that from the approved support corpus."


def test_build_refusal_from_retrieval_decision_maps_insufficient_evidence() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.82, 0.44, 0.41]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    response = build_refusal_from_retrieval_decision(
        decision,
        next_step="ask a narrower question using the product names you need",
    )

    assert (
        map_retrieval_decision_to_reason_code(decision) is RefusalReasonCode.INSUFFICIENT_EVIDENCE
    )
    assert response.refusal.reason_code is RefusalReasonCode.INSUFFICIENT_EVIDENCE
    assert response.final_answer.endswith(
        "Next step: ask a narrower question using the product names you need."
    )


def test_build_refusal_from_retrieval_decision_rejects_non_refusal_actions() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.94, 0.82, 0.76, 0.40]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    with pytest.raises(ValueError, match="does not correspond to a refusal reason code"):
        build_refusal_from_retrieval_decision(decision)


def test_build_refusal_from_citation_validation_maps_failed_result() -> None:
    result = CitationValidationResult(
        outcome=CitationValidationOutcome.RETRY,
        failures=(
            CitationValidationFailure(
                code=CitationValidationFailureCode.MISSING_CITATION_COVERAGE,
                message="Every supported claim must include a citation marker",
                claim_text="A Pod is the smallest deployable unit in Kubernetes.",
            ),
        ),
    )

    response = build_refusal_from_citation_validation(result)

    assert (
        map_citation_validation_to_reason_code(result)
        is RefusalReasonCode.CITATION_VALIDATION_FAILED
    )
    assert response.refusal.reason_code is RefusalReasonCode.CITATION_VALIDATION_FAILED
    assert response.final_answer == (
        "I can’t provide a supported answer because the citations could not be validated."
    )


def test_build_refusal_from_citation_validation_rejects_valid_result() -> None:
    result = CitationValidationResult(outcome=CitationValidationOutcome.VALID)

    with pytest.raises(ValueError, match="must contain failures"):
        build_refusal_from_citation_validation(result)
