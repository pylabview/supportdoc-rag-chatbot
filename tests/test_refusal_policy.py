from __future__ import annotations

from pathlib import Path

import pytest

from supportdoc_rag_chatbot.app.schemas import RefusalReasonCode
from supportdoc_rag_chatbot.app.services import (
    RetrievalEvidenceHit,
    RetrievalGateCondition,
    RetrievalScoreNormalization,
    RetrievalSufficiencyAction,
    RetrievalSufficiencyRequest,
    RetrievalSufficiencyThresholds,
    evaluate_retrieval_sufficiency,
    load_retrieval_sufficiency_thresholds,
    summarize_retrieval_scores,
)

DEFAULT_THRESHOLDS = RetrievalSufficiencyThresholds(
    score_normalization=RetrievalScoreNormalization.UNIT_INTERVAL,
    k=8,
    T_top1=0.75,
    T_mean3=0.60,
    T_support=0.55,
    N_support=2,
    L_thin_max=3,
    T_nohit=0.20,
)


def make_request(
    scores: list[float],
    *,
    score_normalization: RetrievalScoreNormalization = RetrievalScoreNormalization.UNIT_INTERVAL,
) -> RetrievalSufficiencyRequest:
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
        score_normalization=score_normalization,
    )


def test_load_retrieval_sufficiency_thresholds_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "trust-config.yaml"
    config_path.write_text(
        """
trust:
  retrieval_sufficiency:
    score_normalization: unit_interval
    k: 5
    T_top1: 0.8
    T_mean3: 0.65
    T_support: 0.5
    N_support: 2
    L_thin_max: 2
    T_nohit: 0.15
""".strip()
        + "\n",
        encoding="utf-8",
    )

    thresholds = load_retrieval_sufficiency_thresholds(config_path)

    assert thresholds.k == 5
    assert thresholds.T_top1 == pytest.approx(0.8)
    assert thresholds.T_mean3 == pytest.approx(0.65)
    assert thresholds.T_support == pytest.approx(0.5)
    assert thresholds.N_support == 2
    assert thresholds.L_thin_max == 2
    assert thresholds.T_nohit == pytest.approx(0.15)
    assert thresholds.score_normalization is RetrievalScoreNormalization.UNIT_INTERVAL


def test_summarize_retrieval_scores_uses_top_k_and_support_threshold() -> None:
    request = make_request([0.90, 0.62, 0.40, 0.95])
    thresholds = RetrievalSufficiencyThresholds(
        score_normalization=RetrievalScoreNormalization.UNIT_INTERVAL,
        k=3,
        T_top1=0.75,
        T_mean3=0.60,
        T_support=0.60,
        N_support=2,
        L_thin_max=3,
        T_nohit=0.20,
    )

    summary = summarize_retrieval_scores(request, thresholds=thresholds)

    assert summary.available_hit_count == 4
    assert summary.considered_hit_count == 3
    assert summary.considered_chunk_ids == ("chunk-1", "chunk-2", "chunk-3")
    assert summary.top1_score == pytest.approx(0.90)
    assert summary.mean_top3_score == pytest.approx((0.90 + 0.62 + 0.40) / 3)
    assert summary.support_count == 2
    assert summary.support_chunk_ids == ("chunk-1", "chunk-2")


def test_evaluate_retrieval_sufficiency_allows_full_answer() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.94, 0.82, 0.76, 0.40]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert decision.action is RetrievalSufficiencyAction.ALLOW_FULL_ANSWER
    assert decision.allow_generation is True
    assert decision.allow_full_answer is True
    assert decision.allow_thin_answer is False
    assert decision.should_refuse is False
    assert decision.refusal_reason_code is None
    assert decision.max_answer_sentences is None
    assert decision.diagnostics.failing_conditions == ()
    assert decision.diagnostics.thin_reasons == ()


def test_evaluate_retrieval_sufficiency_allows_thin_answer_on_threshold_boundary() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.75, 0.60, 0.45]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert decision.action is RetrievalSufficiencyAction.ALLOW_THIN_ANSWER
    assert decision.max_answer_sentences == 3
    assert decision.diagnostics.summary.top1_score == pytest.approx(0.75)
    assert decision.diagnostics.summary.mean_top3_score == pytest.approx(0.60)
    assert decision.diagnostics.summary.support_count == 2
    assert decision.diagnostics.thin_reasons == (RetrievalGateCondition.SUPPORT_FLOOR_ONLY,)


def test_evaluate_retrieval_sufficiency_allows_thin_answer_for_sparse_context() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.90, 0.70]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert decision.action is RetrievalSufficiencyAction.ALLOW_THIN_ANSWER
    assert decision.max_answer_sentences == 3
    assert RetrievalGateCondition.SPARSE_CONTEXT in decision.diagnostics.thin_reasons
    assert RetrievalGateCondition.SUPPORT_FLOOR_ONLY in decision.diagnostics.thin_reasons


def test_evaluate_retrieval_sufficiency_refuses_no_relevant_docs() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.19, 0.10]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert decision.action is RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS
    assert decision.refusal_reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
    assert decision.should_refuse is True
    assert decision.allow_generation is False
    assert decision.diagnostics.failing_conditions == (RetrievalGateCondition.NO_HIT_FLOOR,)


def test_evaluate_retrieval_sufficiency_refuses_for_low_mean3_and_support_shortfall() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.82, 0.44, 0.41]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert decision.action is RetrievalSufficiencyAction.REFUSE_INSUFFICIENT_EVIDENCE
    assert decision.refusal_reason_code is RefusalReasonCode.INSUFFICIENT_EVIDENCE
    assert decision.max_answer_sentences is None
    assert RetrievalGateCondition.LOW_MEAN3 in decision.diagnostics.failing_conditions
    assert RetrievalGateCondition.INSUFFICIENT_SUPPORT in decision.diagnostics.failing_conditions


def test_evaluate_retrieval_sufficiency_refuses_when_no_hits_are_available() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    assert decision.action is RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS
    assert decision.refusal_reason_code is RefusalReasonCode.NO_RELEVANT_DOCS
    assert decision.diagnostics.summary.considered_hit_count == 0


def test_evaluate_retrieval_sufficiency_rejects_normalization_mismatch() -> None:
    request = make_request(
        [1.8, 1.4, 0.9],
        score_normalization=RetrievalScoreNormalization.RAW,
    )

    with pytest.raises(ValueError, match="require unit_interval scores"):
        evaluate_retrieval_sufficiency(request, thresholds=DEFAULT_THRESHOLDS)


def test_retrieval_sufficiency_decision_to_dict_is_machine_readable() -> None:
    decision = evaluate_retrieval_sufficiency(
        make_request([0.75, 0.60, 0.45]),
        thresholds=DEFAULT_THRESHOLDS,
    )

    payload = decision.to_dict()

    assert payload["action"] == "allow_thin_answer"
    assert payload["refusal_reason_code"] is None
    assert payload["max_answer_sentences"] == 3
    assert payload["diagnostics"]["thresholds"]["T_top1"] == pytest.approx(0.75)
    assert payload["diagnostics"]["summary"]["support_count"] == 2
    assert payload["diagnostics"]["thin_reasons"] == ["support_floor_only"]
