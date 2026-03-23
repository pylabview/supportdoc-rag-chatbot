from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any, Sequence

from supportdoc_rag_chatbot.app.schemas import RefusalReasonCode
from supportdoc_rag_chatbot.evaluation.harness import RetrievalHit


class RetrievalScoreNormalization(StrEnum):
    """How retrieval scores were normalized before sufficiency gating."""

    UNIT_INTERVAL = "unit_interval"
    RAW = "raw"


class RetrievalGateCondition(StrEnum):
    """Machine-readable diagnostics emitted by retrieval sufficiency gating."""

    NO_HIT_FLOOR = "no_hit_floor"
    LOW_TOP1 = "low_top1"
    LOW_MEAN3 = "low_mean3"
    INSUFFICIENT_SUPPORT = "insufficient_support"
    SPARSE_CONTEXT = "sparse_context"
    SUPPORT_FLOOR_ONLY = "support_floor_only"


class RetrievalSufficiencyAction(StrEnum):
    """Deterministic backend actions emitted before generation."""

    ALLOW_FULL_ANSWER = "allow_full_answer"
    ALLOW_THIN_ANSWER = "allow_thin_answer"
    REFUSE_NO_RELEVANT_DOCS = "refuse_no_relevant_docs"
    REFUSE_INSUFFICIENT_EVIDENCE = "refuse_insufficient_evidence"


@dataclass(slots=True, frozen=True)
class RetrievalEvidenceHit:
    """Minimal retrieval-hit view consumed by trust-layer sufficiency gating."""

    chunk_id: str
    score: float
    rank: int
    doc_id: str | None = None
    section_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "chunk_id", _validate_required_string(self.chunk_id, field_name="chunk_id")
        )
        object.__setattr__(self, "score", _validate_finite_float(self.score, field_name="score"))
        if self.rank <= 0:
            raise ValueError("rank must be > 0")
        object.__setattr__(self, "doc_id", _normalize_optional_string(self.doc_id))
        object.__setattr__(self, "section_id", _normalize_optional_string(self.section_id))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_retrieval_hit(cls, hit: RetrievalHit) -> "RetrievalEvidenceHit":
        return cls(
            chunk_id=hit.chunk_id,
            score=hit.score,
            rank=hit.rank,
            doc_id=hit.doc_id,
            section_id=hit.section_id,
            metadata=dict(hit.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RetrievalSufficiencyThresholds:
    """Configurable trust-policy thresholds for retrieval sufficiency gating."""

    k: int
    T_top1: float
    T_mean3: float
    T_support: float
    N_support: int
    L_thin_max: int
    T_nohit: float | None = None
    score_normalization: RetrievalScoreNormalization = RetrievalScoreNormalization.UNIT_INTERVAL

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError("k must be > 0")
        if self.N_support <= 0:
            raise ValueError("N_support must be > 0")
        if self.L_thin_max <= 0:
            raise ValueError("L_thin_max must be > 0")

        object.__setattr__(self, "T_top1", _validate_finite_float(self.T_top1, field_name="T_top1"))
        object.__setattr__(
            self, "T_mean3", _validate_finite_float(self.T_mean3, field_name="T_mean3")
        )
        object.__setattr__(
            self,
            "T_support",
            _validate_finite_float(self.T_support, field_name="T_support"),
        )
        if self.T_nohit is not None:
            object.__setattr__(
                self,
                "T_nohit",
                _validate_finite_float(self.T_nohit, field_name="T_nohit"),
            )

        if self.score_normalization is RetrievalScoreNormalization.UNIT_INTERVAL:
            _validate_unit_interval(self.T_top1, field_name="T_top1")
            _validate_unit_interval(self.T_mean3, field_name="T_mean3")
            _validate_unit_interval(self.T_support, field_name="T_support")
            if self.T_nohit is not None:
                _validate_unit_interval(self.T_nohit, field_name="T_nohit")

        if self.T_nohit is not None and self.T_nohit > self.T_top1:
            raise ValueError("T_nohit must be <= T_top1")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalSufficiencyThresholds":
        return cls(
            k=int(payload["k"]),
            T_top1=float(payload["T_top1"]),
            T_mean3=float(payload["T_mean3"]),
            T_support=float(payload["T_support"]),
            N_support=int(payload["N_support"]),
            L_thin_max=int(payload["L_thin_max"]),
            T_nohit=(float(payload["T_nohit"]) if payload.get("T_nohit") is not None else None),
            score_normalization=RetrievalScoreNormalization(
                payload.get("score_normalization", RetrievalScoreNormalization.UNIT_INTERVAL.value)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score_normalization"] = self.score_normalization.value
        return payload


@dataclass(slots=True, frozen=True)
class RetrievalSufficiencyRequest:
    """Request-scoped retrieval evidence passed into sufficiency gating."""

    hits: tuple[RetrievalEvidenceHit, ...]
    score_normalization: RetrievalScoreNormalization = RetrievalScoreNormalization.UNIT_INTERVAL
    retriever_name: str | None = None
    retriever_type: str | None = None
    query_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        sorted_hits = tuple(sorted(self.hits, key=lambda hit: (hit.rank, hit.chunk_id)))
        object.__setattr__(self, "hits", sorted_hits)
        object.__setattr__(self, "retriever_name", _normalize_optional_string(self.retriever_name))
        object.__setattr__(self, "retriever_type", _normalize_optional_string(self.retriever_type))
        object.__setattr__(self, "query_id", _normalize_optional_string(self.query_id))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.score_normalization is RetrievalScoreNormalization.UNIT_INTERVAL:
            for hit in sorted_hits:
                _validate_unit_interval(hit.score, field_name=f"score for chunk_id={hit.chunk_id}")

    @classmethod
    def from_retrieval_hits(
        cls,
        hits: Sequence[RetrievalHit],
        *,
        score_normalization: RetrievalScoreNormalization = RetrievalScoreNormalization.UNIT_INTERVAL,
        retriever_name: str | None = None,
        retriever_type: str | None = None,
        query_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "RetrievalSufficiencyRequest":
        return cls(
            hits=tuple(RetrievalEvidenceHit.from_retrieval_hit(hit) for hit in hits),
            score_normalization=score_normalization,
            retriever_name=retriever_name,
            retriever_type=retriever_type,
            query_id=query_id,
            metadata=(dict(metadata) if metadata is not None else {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": [hit.to_dict() for hit in self.hits],
            "score_normalization": self.score_normalization.value,
            "retriever_name": self.retriever_name,
            "retriever_type": self.retriever_type,
            "query_id": self.query_id,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True, frozen=True)
class RetrievalScoreSummary:
    """Aggregated retrieval-score features used by sufficiency gating."""

    available_hit_count: int
    considered_hit_count: int
    top1_score: float | None
    mean_top3_score: float | None
    mean_top3_window: int
    support_count: int
    considered_chunk_ids: tuple[str, ...]
    support_chunk_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RetrievalSufficiencyDiagnostics:
    """Machine-readable diagnostics suitable for structured logging."""

    thresholds: RetrievalSufficiencyThresholds
    summary: RetrievalScoreSummary
    score_normalization: RetrievalScoreNormalization
    failing_conditions: tuple[RetrievalGateCondition, ...] = ()
    thin_reasons: tuple[RetrievalGateCondition, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "thresholds": self.thresholds.to_dict(),
            "summary": self.summary.to_dict(),
            "score_normalization": self.score_normalization.value,
            "failing_conditions": [condition.value for condition in self.failing_conditions],
            "thin_reasons": [reason.value for reason in self.thin_reasons],
        }


@dataclass(slots=True, frozen=True)
class RetrievalSufficiencyDecision:
    """Backend-facing action emitted by deterministic retrieval sufficiency gating."""

    action: RetrievalSufficiencyAction
    diagnostics: RetrievalSufficiencyDiagnostics
    max_answer_sentences: int | None = None

    @property
    def allow_generation(self) -> bool:
        return self.action in {
            RetrievalSufficiencyAction.ALLOW_FULL_ANSWER,
            RetrievalSufficiencyAction.ALLOW_THIN_ANSWER,
        }

    @property
    def allow_full_answer(self) -> bool:
        return self.action is RetrievalSufficiencyAction.ALLOW_FULL_ANSWER

    @property
    def allow_thin_answer(self) -> bool:
        return self.action is RetrievalSufficiencyAction.ALLOW_THIN_ANSWER

    @property
    def should_refuse(self) -> bool:
        return self.action in {
            RetrievalSufficiencyAction.REFUSE_INSUFFICIENT_EVIDENCE,
            RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS,
        }

    @property
    def refusal_reason_code(self) -> RefusalReasonCode | None:
        if self.action is RetrievalSufficiencyAction.REFUSE_NO_RELEVANT_DOCS:
            return RefusalReasonCode.NO_RELEVANT_DOCS
        if self.action is RetrievalSufficiencyAction.REFUSE_INSUFFICIENT_EVIDENCE:
            return RefusalReasonCode.INSUFFICIENT_EVIDENCE
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "refusal_reason_code": (
                self.refusal_reason_code.value if self.refusal_reason_code is not None else None
            ),
            "max_answer_sentences": self.max_answer_sentences,
            "diagnostics": self.diagnostics.to_dict(),
        }


def _validate_required_string(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_finite_float(value: float, *, field_name: str) -> float:
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be a finite float")
    return normalized


def _validate_unit_interval(value: float, *, field_name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0 for unit_interval scores")
