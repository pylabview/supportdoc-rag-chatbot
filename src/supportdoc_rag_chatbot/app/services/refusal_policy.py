from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .policy_types import (
    RetrievalEvidenceHit,
    RetrievalGateCondition,
    RetrievalScoreSummary,
    RetrievalSufficiencyAction,
    RetrievalSufficiencyDecision,
    RetrievalSufficiencyDiagnostics,
    RetrievalSufficiencyRequest,
    RetrievalSufficiencyThresholds,
)

DEFAULT_TRUST_POLICY_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "resources/default_config.yaml"
)


@dataclass(slots=True)
class RetrievalSufficiencySmokeReport:
    config_path: str
    thresholds: dict[str, Any]
    full_answer_action: str
    thin_answer_action: str
    nohit_action: str
    insufficient_action: str


def load_retrieval_sufficiency_thresholds(
    config_path: Path = DEFAULT_TRUST_POLICY_CONFIG_PATH,
) -> RetrievalSufficiencyThresholds:
    """Load the canonical retrieval sufficiency thresholds from YAML config."""

    _require_path(config_path, label="Trust policy config")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Trust policy config must be a YAML mapping")

    trust_config = payload.get("trust", {})
    if not isinstance(trust_config, dict):
        raise ValueError("trust config must be a YAML mapping")

    gating_config = trust_config.get("retrieval_sufficiency", {})
    if not isinstance(gating_config, dict):
        raise ValueError("trust.retrieval_sufficiency must be a YAML mapping")

    return RetrievalSufficiencyThresholds.from_dict(gating_config)


def summarize_retrieval_scores(
    request: RetrievalSufficiencyRequest,
    *,
    thresholds: RetrievalSufficiencyThresholds,
) -> RetrievalScoreSummary:
    """Aggregate top-score, mean-score, and support-count features for gating."""

    _validate_score_normalization(request=request, thresholds=thresholds)

    considered_hits = request.hits[: thresholds.k]
    top1_score = considered_hits[0].score if considered_hits else None
    mean_window = min(3, len(considered_hits))
    mean_top3_score = None
    if mean_window:
        mean_top3_score = sum(hit.score for hit in considered_hits[:mean_window]) / mean_window
    support_hits = tuple(hit for hit in considered_hits if hit.score >= thresholds.T_support)

    return RetrievalScoreSummary(
        available_hit_count=len(request.hits),
        considered_hit_count=len(considered_hits),
        top1_score=top1_score,
        mean_top3_score=mean_top3_score,
        mean_top3_window=mean_window,
        support_count=len(support_hits),
        considered_chunk_ids=tuple(hit.chunk_id for hit in considered_hits),
        support_chunk_ids=tuple(hit.chunk_id for hit in support_hits),
    )


def evaluate_retrieval_sufficiency(
    request: RetrievalSufficiencyRequest,
    *,
    thresholds: RetrievalSufficiencyThresholds | None = None,
) -> RetrievalSufficiencyDecision:
    """Decide whether retrieval evidence is strong enough for full, thin, or refused generation."""

    resolved_thresholds = thresholds or load_retrieval_sufficiency_thresholds()
    summary = summarize_retrieval_scores(request, thresholds=resolved_thresholds)

    if summary.considered_hit_count == 0:
        diagnostics = RetrievalSufficiencyDiagnostics(
            thresholds=resolved_thresholds,
            summary=summary,
            score_normalization=request.score_normalization,
            failing_conditions=(RetrievalGateCondition.NO_HIT_FLOOR,),
        )
        return RetrievalSufficiencyDecision(
            action=RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS,
            diagnostics=diagnostics,
        )

    failing_conditions: list[RetrievalGateCondition] = []
    if resolved_thresholds.T_nohit is not None and summary.top1_score is not None:
        if summary.top1_score < resolved_thresholds.T_nohit:
            failing_conditions.append(RetrievalGateCondition.NO_HIT_FLOOR)
            diagnostics = RetrievalSufficiencyDiagnostics(
                thresholds=resolved_thresholds,
                summary=summary,
                score_normalization=request.score_normalization,
                failing_conditions=tuple(failing_conditions),
            )
            return RetrievalSufficiencyDecision(
                action=RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS,
                diagnostics=diagnostics,
            )

    if summary.top1_score is None or summary.top1_score < resolved_thresholds.T_top1:
        failing_conditions.append(RetrievalGateCondition.LOW_TOP1)
    if summary.mean_top3_score is None or summary.mean_top3_score < resolved_thresholds.T_mean3:
        failing_conditions.append(RetrievalGateCondition.LOW_MEAN3)
    if summary.support_count < resolved_thresholds.N_support:
        failing_conditions.append(RetrievalGateCondition.INSUFFICIENT_SUPPORT)

    if failing_conditions:
        diagnostics = RetrievalSufficiencyDiagnostics(
            thresholds=resolved_thresholds,
            summary=summary,
            score_normalization=request.score_normalization,
            failing_conditions=tuple(failing_conditions),
        )
        return RetrievalSufficiencyDecision(
            action=RetrievalSufficiencyAction.REFUSE_INSUFFICIENT_EVIDENCE,
            diagnostics=diagnostics,
        )

    thin_reasons: list[RetrievalGateCondition] = []
    if summary.support_count == resolved_thresholds.N_support:
        thin_reasons.append(RetrievalGateCondition.SUPPORT_FLOOR_ONLY)
    if summary.mean_top3_window < 3:
        thin_reasons.append(RetrievalGateCondition.SPARSE_CONTEXT)

    diagnostics = RetrievalSufficiencyDiagnostics(
        thresholds=resolved_thresholds,
        summary=summary,
        score_normalization=request.score_normalization,
        thin_reasons=tuple(thin_reasons),
    )
    if thin_reasons:
        return RetrievalSufficiencyDecision(
            action=RetrievalSufficiencyAction.ALLOW_THIN_ANSWER,
            diagnostics=diagnostics,
            max_answer_sentences=resolved_thresholds.L_thin_max,
        )
    return RetrievalSufficiencyDecision(
        action=RetrievalSufficiencyAction.ALLOW_FULL_ANSWER,
        diagnostics=diagnostics,
    )


def run_retrieval_sufficiency_smoke(
    *,
    config_path: Path = DEFAULT_TRUST_POLICY_CONFIG_PATH,
) -> RetrievalSufficiencySmokeReport:
    """Exercise deterministic allow/thin/refuse branches against checked-in thresholds."""

    thresholds = load_retrieval_sufficiency_thresholds(config_path)

    full_answer_decision = evaluate_retrieval_sufficiency(
        _build_request([0.94, 0.82, 0.76]),
        thresholds=thresholds,
    )
    thin_answer_decision = evaluate_retrieval_sufficiency(
        _build_request([0.85, 0.57, 0.39]),
        thresholds=thresholds,
    )
    nohit_decision = evaluate_retrieval_sufficiency(
        _build_request([0.10, 0.08]),
        thresholds=thresholds,
    )
    insufficient_decision = evaluate_retrieval_sufficiency(
        _build_request([0.82, 0.44, 0.41]),
        thresholds=thresholds,
    )

    expected_actions = {
        "full": RetrievalSufficiencyAction.ALLOW_FULL_ANSWER,
        "thin": RetrievalSufficiencyAction.ALLOW_THIN_ANSWER,
        "nohit": RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS,
        "insufficient": RetrievalSufficiencyAction.REFUSE_INSUFFICIENT_EVIDENCE,
    }
    observed_actions = {
        "full": full_answer_decision.action,
        "thin": thin_answer_decision.action,
        "nohit": nohit_decision.action,
        "insufficient": insufficient_decision.action,
    }
    for label, expected_action in expected_actions.items():
        observed_action = observed_actions[label]
        if observed_action is not expected_action:
            raise ValueError(
                f"Retrieval sufficiency smoke case {label!r} expected {expected_action.value} "
                f"but got {observed_action.value}"
            )

    return RetrievalSufficiencySmokeReport(
        config_path=str(config_path),
        thresholds=thresholds.to_dict(),
        full_answer_action=full_answer_decision.action.value,
        thin_answer_action=thin_answer_decision.action.value,
        nohit_action=nohit_decision.action.value,
        insufficient_action=insufficient_decision.action.value,
    )


def render_retrieval_sufficiency_smoke_report(report: RetrievalSufficiencySmokeReport) -> str:
    return "\n".join(
        [
            "Retrieval sufficiency smoke test",
            f"config: {report.config_path}",
            (
                "thresholds: "
                f"k={report.thresholds['k']}, "
                f"T_top1={report.thresholds['T_top1']}, "
                f"T_mean3={report.thresholds['T_mean3']}, "
                f"T_support={report.thresholds['T_support']}, "
                f"N_support={report.thresholds['N_support']}, "
                f"L_thin_max={report.thresholds['L_thin_max']}, "
                f"T_nohit={report.thresholds['T_nohit']}"
            ),
            f"full answer case: {report.full_answer_action}",
            f"thin answer case: {report.thin_answer_action}",
            f"no-hit case: {report.nohit_action}",
            f"insufficient-evidence case: {report.insufficient_action}",
            "status: ok",
        ]
    )


def _build_request(scores: list[float]) -> RetrievalSufficiencyRequest:
    return RetrievalSufficiencyRequest(
        hits=tuple(
            RetrievalEvidenceHit(
                chunk_id=f"chunk-{index:04d}",
                score=score,
                rank=index,
                doc_id=f"doc-{index:04d}",
                section_id=f"section-{index:04d}",
            )
            for index, score in enumerate(scores, start=1)
        )
    )


def _require_path(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} is not a file: {path}")


def _validate_score_normalization(
    *,
    request: RetrievalSufficiencyRequest,
    thresholds: RetrievalSufficiencyThresholds,
) -> None:
    if request.score_normalization is not thresholds.score_normalization:
        raise ValueError(
            "Retrieval sufficiency thresholds require "
            f"{thresholds.score_normalization.value} scores but request provided "
            f"{request.score_normalization.value}"
        )
