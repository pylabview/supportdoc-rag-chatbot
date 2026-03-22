from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Sequence

from supportdoc_rag_chatbot.app.schemas import (
    DEFAULT_TRUST_ANSWER_FIXTURE_PATH,
    DEFAULT_TRUST_REFUSAL_FIXTURE_PATH,
    QueryResponse,
)
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord

from .sentence_splitter import ClaimSpan, split_answer_claims

DEFAULT_CITATION_VALIDATOR_CONTEXT_FIXTURE_PATH = Path(
    "docs/contracts/query_response.retrieved_context.example.json"
)
_VALID_MARKER_RE = re.compile(r"\[(?P<index>\d+)\]")
_BRACKET_TOKEN_RE = re.compile(r"\[[^\[\]\n]*\]")
_REFUSAL_TEXT_CUES = (
    "can't answer",
    "cannot answer",
    "do not know",
    "don't know",
    "no relevant documentation",
    "no relevant docs",
    "insufficient evidence",
    "out of scope",
    "approved support corpus",
)


class CitationValidationOutcome(StrEnum):
    """Next action the backend should take after deterministic validation."""

    VALID = "valid"
    RETRY = "retry"
    REFUSE = "refuse"


class CitationValidationFailureCode(StrEnum):
    """Machine-readable citation validation failure categories."""

    MISSING_CITATION_COVERAGE = "missing_citation_coverage"
    MALFORMED_CITATION_MARKER = "malformed_citation_marker"
    UNKNOWN_CITATION_MARKER = "unknown_citation_marker"
    DUPLICATE_CITATION_MARKER = "duplicate_citation_marker"
    NON_RETRIEVED_CHUNK = "non_retrieved_chunk"
    OFFSET_OUT_OF_RANGE = "offset_out_of_range"
    REFUSAL_ANSWER_CONTRADICTION = "refusal_answer_contradiction"


@dataclass(slots=True, frozen=True)
class CitationMarkerMatch:
    """One parsed numeric citation marker inside generated answer text."""

    marker: str
    start_offset: int
    end_offset: int


@dataclass(slots=True, frozen=True)
class RetrievedChunkCitationContext:
    """Minimal retrieved-chunk metadata needed by the citation validator."""

    doc_id: str
    chunk_id: str
    start_offset: int
    end_offset: int
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "doc_id", _validate_required_string(self.doc_id, field_name="doc_id")
        )
        object.__setattr__(
            self,
            "chunk_id",
            _validate_required_string(self.chunk_id, field_name="chunk_id"),
        )
        object.__setattr__(self, "text", _validate_required_string(self.text, field_name="text"))
        if self.start_offset < 0:
            raise ValueError("start_offset must be >= 0")
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")

    @classmethod
    def from_chunk_record(cls, chunk: ChunkRecord) -> "RetrievedChunkCitationContext":
        return cls(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            text=chunk.text,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievedChunkCitationContext":
        return cls(
            doc_id=str(payload["doc_id"]),
            chunk_id=str(payload["chunk_id"]),
            start_offset=int(payload["start_offset"]),
            end_offset=int(payload["end_offset"]),
            text=str(payload["text"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def text_length(self) -> int:
        return len(self.text)


@dataclass(slots=True, frozen=True)
class CitationValidationFailure:
    """Structured citation-validation failure returned to the backend."""

    code: CitationValidationFailureCode
    message: str
    claim_text: str | None = None
    marker: str | None = None
    chunk_id: str | None = None


@dataclass(slots=True, frozen=True)
class CitationValidationResult:
    """Deterministic citation-validation outcome plus structured failure reasons."""

    outcome: CitationValidationOutcome
    failures: tuple[CitationValidationFailure, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.outcome is CitationValidationOutcome.VALID

    @property
    def should_retry(self) -> bool:
        return self.outcome is CitationValidationOutcome.RETRY

    @property
    def should_refuse(self) -> bool:
        return self.outcome is CitationValidationOutcome.REFUSE


@dataclass(slots=True)
class CitationValidatorSmokeReport:
    answer_fixture_path: str
    refusal_fixture_path: str
    retrieved_context_fixture_path: str
    answer_outcome: str
    refusal_outcome: str
    retrieved_chunk_count: int
    answer_failure_count: int = 0
    refusal_failure_count: int = 0


def validate_query_response_citations(
    response: QueryResponse,
    *,
    retrieved_chunks: Sequence[RetrievedChunkCitationContext | ChunkRecord],
) -> CitationValidationResult:
    """Validate sentence-level citation coverage against request-scoped retrieved chunks."""

    normalized_chunks = tuple(_coerce_retrieved_chunk(chunk) for chunk in retrieved_chunks)
    if response.refusal.is_refusal:
        return _validate_refusal_response(response)

    failures: list[CitationValidationFailure] = []
    citation_record_map = build_citation_record_map(response.citations, failures=failures)
    retrieved_chunk_map = build_retrieved_chunk_map(normalized_chunks)

    for claim in split_answer_claims(response.final_answer):
        failures.extend(
            _validate_claim(
                claim=claim,
                citation_record_map=citation_record_map,
                retrieved_chunk_map=retrieved_chunk_map,
            )
        )

    if not failures:
        return CitationValidationResult(outcome=CitationValidationOutcome.VALID)
    return CitationValidationResult(
        outcome=CitationValidationOutcome.RETRY,
        failures=tuple(failures),
    )


def build_citation_record_map(
    citations: Sequence,
    *,
    failures: list[CitationValidationFailure] | None = None,
) -> dict[str, Any]:
    """Map citation markers to records while collecting deterministic marker failures."""

    collected_failures = failures if failures is not None else []
    mapping: dict[str, Any] = {}

    for citation in citations:
        if not _VALID_MARKER_RE.fullmatch(citation.marker):
            collected_failures.append(
                CitationValidationFailure(
                    code=CitationValidationFailureCode.MALFORMED_CITATION_MARKER,
                    message=(
                        f"Citation record marker {citation.marker!r} must use bracketed numeric form "
                        "such as [1]"
                    ),
                    marker=citation.marker,
                    chunk_id=citation.chunk_id,
                )
            )
            continue

        if citation.marker in mapping:
            collected_failures.append(
                CitationValidationFailure(
                    code=CitationValidationFailureCode.DUPLICATE_CITATION_MARKER,
                    message=f"Citation marker {citation.marker} is duplicated in citations",
                    marker=citation.marker,
                    chunk_id=citation.chunk_id,
                )
            )
            continue

        mapping[citation.marker] = citation

    return mapping


def build_retrieved_chunk_map(
    retrieved_chunks: Sequence[RetrievedChunkCitationContext | ChunkRecord],
) -> dict[str, RetrievedChunkCitationContext]:
    """Map request-scoped retrieved chunks by chunk_id."""

    return {
        normalized.chunk_id: normalized
        for normalized in (_coerce_retrieved_chunk(chunk) for chunk in retrieved_chunks)
    }


def extract_citation_markers(text: str) -> tuple[CitationMarkerMatch, ...]:
    """Return all valid bracketed numeric markers from text."""

    return tuple(
        CitationMarkerMatch(
            marker=match.group(0),
            start_offset=match.start(),
            end_offset=match.end(),
        )
        for match in _VALID_MARKER_RE.finditer(text)
    )


def find_malformed_citation_markers(text: str) -> tuple[str, ...]:
    """Return bracketed marker-like tokens that are not valid numeric citations."""

    malformed: list[str] = []
    for token in _BRACKET_TOKEN_RE.finditer(text):
        marker = token.group(0)
        if _VALID_MARKER_RE.fullmatch(marker) is None:
            malformed.append(marker)
    return tuple(malformed)


def load_retrieved_chunk_contexts(path: Path) -> list[RetrievedChunkCitationContext]:
    """Load deterministic retrieved-context fixtures from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Retrieved context fixture must be a JSON list")
    return [RetrievedChunkCitationContext.from_dict(item) for item in payload]


def run_citation_validator_smoke(
    *,
    answer_fixture_path: Path = DEFAULT_TRUST_ANSWER_FIXTURE_PATH,
    refusal_fixture_path: Path = DEFAULT_TRUST_REFUSAL_FIXTURE_PATH,
    retrieved_context_fixture_path: Path = DEFAULT_CITATION_VALIDATOR_CONTEXT_FIXTURE_PATH,
) -> CitationValidatorSmokeReport:
    """Validate the checked-in example answer and refusal with deterministic retrieved context."""

    _require_path(answer_fixture_path, label="Trust answer fixture")
    _require_path(refusal_fixture_path, label="Trust refusal fixture")
    _require_path(retrieved_context_fixture_path, label="Retrieved context fixture")

    answer_response = QueryResponse.model_validate(_read_json(answer_fixture_path))
    refusal_response = QueryResponse.model_validate(_read_json(refusal_fixture_path))
    retrieved_context = load_retrieved_chunk_contexts(retrieved_context_fixture_path)

    answer_result = validate_query_response_citations(
        answer_response,
        retrieved_chunks=retrieved_context,
    )
    if not answer_result.is_valid:
        raise ValueError(
            "Answer fixture failed citation validation: "
            f"{_render_failure_messages(answer_result.failures)}"
        )

    refusal_result = validate_query_response_citations(
        refusal_response,
        retrieved_chunks=(),
    )
    if not refusal_result.is_valid:
        raise ValueError(
            "Refusal fixture failed citation validation: "
            f"{_render_failure_messages(refusal_result.failures)}"
        )

    return CitationValidatorSmokeReport(
        answer_fixture_path=str(answer_fixture_path),
        refusal_fixture_path=str(refusal_fixture_path),
        retrieved_context_fixture_path=str(retrieved_context_fixture_path),
        answer_outcome=answer_result.outcome.value,
        refusal_outcome=refusal_result.outcome.value,
        retrieved_chunk_count=len(retrieved_context),
        answer_failure_count=len(answer_result.failures),
        refusal_failure_count=len(refusal_result.failures),
    )


def render_citation_validator_smoke_report(report: CitationValidatorSmokeReport) -> str:
    return "\n".join(
        [
            "Citation validator smoke test",
            f"answer fixture: {report.answer_fixture_path} (outcome={report.answer_outcome})",
            f"refusal fixture: {report.refusal_fixture_path} (outcome={report.refusal_outcome})",
            (
                "retrieved context: "
                f"{report.retrieved_context_fixture_path} (chunks={report.retrieved_chunk_count})"
            ),
            (
                "failure counts: "
                f"answer={report.answer_failure_count}, refusal={report.refusal_failure_count}"
            ),
            "status: ok",
        ]
    )


def _validate_claim(
    *,
    claim: ClaimSpan,
    citation_record_map: dict[str, Any],
    retrieved_chunk_map: dict[str, RetrievedChunkCitationContext],
) -> list[CitationValidationFailure]:
    failures: list[CitationValidationFailure] = []
    marker_matches = extract_citation_markers(claim.text)
    malformed_markers = find_malformed_citation_markers(claim.text)

    for marker in malformed_markers:
        failures.append(
            CitationValidationFailure(
                code=CitationValidationFailureCode.MALFORMED_CITATION_MARKER,
                message=f"Claim contains malformed citation marker {marker!r}",
                claim_text=claim.text,
                marker=marker,
            )
        )

    if not marker_matches:
        failures.append(
            CitationValidationFailure(
                code=CitationValidationFailureCode.MISSING_CITATION_COVERAGE,
                message="Every sentence or bullet item must include at least one citation marker",
                claim_text=claim.text,
            )
        )
        return failures

    seen_markers: set[str] = set()
    for marker_match in marker_matches:
        if marker_match.marker in seen_markers:
            continue
        seen_markers.add(marker_match.marker)

        citation_record = citation_record_map.get(marker_match.marker)
        if citation_record is None:
            failures.append(
                CitationValidationFailure(
                    code=CitationValidationFailureCode.UNKNOWN_CITATION_MARKER,
                    message=f"Marker {marker_match.marker} does not resolve to a citation record",
                    claim_text=claim.text,
                    marker=marker_match.marker,
                )
            )
            continue

        failures.extend(
            _validate_citation_record(
                claim=claim,
                marker=marker_match.marker,
                citation_record=citation_record,
                retrieved_chunk_map=retrieved_chunk_map,
            )
        )

    return failures


def _validate_citation_record(
    *,
    claim: ClaimSpan,
    marker: str,
    citation_record,
    retrieved_chunk_map: dict[str, RetrievedChunkCitationContext],
) -> list[CitationValidationFailure]:
    context = retrieved_chunk_map.get(citation_record.chunk_id)
    if context is None:
        return [
            CitationValidationFailure(
                code=CitationValidationFailureCode.NON_RETRIEVED_CHUNK,
                message=(
                    f"Marker {marker} references chunk_id {citation_record.chunk_id!r}, "
                    "which is not present in the request-scoped retrieved context"
                ),
                claim_text=claim.text,
                marker=marker,
                chunk_id=citation_record.chunk_id,
            )
        ]

    absolute_start = context.start_offset + citation_record.start_offset
    absolute_end = context.start_offset + citation_record.end_offset
    if citation_record.end_offset > context.text_length:
        return [
            CitationValidationFailure(
                code=CitationValidationFailureCode.OFFSET_OUT_OF_RANGE,
                message=(
                    f"Marker {marker} span {citation_record.start_offset}:{citation_record.end_offset} "
                    f"falls outside retrieved chunk text length {context.text_length}"
                ),
                claim_text=claim.text,
                marker=marker,
                chunk_id=context.chunk_id,
            )
        ]
    if absolute_start < context.start_offset or absolute_end > context.end_offset:
        return [
            CitationValidationFailure(
                code=CitationValidationFailureCode.OFFSET_OUT_OF_RANGE,
                message=(
                    f"Marker {marker} span {citation_record.start_offset}:{citation_record.end_offset} "
                    "falls outside stored chunk bounds"
                ),
                claim_text=claim.text,
                marker=marker,
                chunk_id=context.chunk_id,
            )
        ]
    return []


def _validate_refusal_response(response: QueryResponse) -> CitationValidationResult:
    failures: list[CitationValidationFailure] = []
    refusal_message = (response.refusal.message or "").strip()
    final_answer = response.final_answer.strip()

    if final_answer != refusal_message:
        failures.append(
            CitationValidationFailure(
                code=CitationValidationFailureCode.REFUSAL_ANSWER_CONTRADICTION,
                message=(
                    "refusal.is_refusal=true requires final_answer to match refusal.message exactly"
                ),
                claim_text=response.final_answer,
            )
        )
    if extract_citation_markers(response.final_answer) or find_malformed_citation_markers(
        response.final_answer
    ):
        failures.append(
            CitationValidationFailure(
                code=CitationValidationFailureCode.REFUSAL_ANSWER_CONTRADICTION,
                message="Refusal answers must not contain citation markers",
                claim_text=response.final_answer,
            )
        )
    if not _looks_like_refusal_text(final_answer):
        failures.append(
            CitationValidationFailure(
                code=CitationValidationFailureCode.REFUSAL_ANSWER_CONTRADICTION,
                message="refusal.is_refusal=true cannot coexist with substantive answer claims",
                claim_text=response.final_answer,
            )
        )

    if not failures:
        return CitationValidationResult(outcome=CitationValidationOutcome.VALID)
    return CitationValidationResult(
        outcome=CitationValidationOutcome.REFUSE,
        failures=tuple(failures),
    )


def _looks_like_refusal_text(text: str) -> bool:
    normalized = text.casefold()
    return any(cue in normalized for cue in _REFUSAL_TEXT_CUES)


def _coerce_retrieved_chunk(
    chunk: RetrievedChunkCitationContext | ChunkRecord,
) -> RetrievedChunkCitationContext:
    if isinstance(chunk, RetrievedChunkCitationContext):
        return chunk
    if isinstance(chunk, ChunkRecord):
        return RetrievedChunkCitationContext.from_chunk_record(chunk)
    raise TypeError(
        "retrieved_chunks entries must be RetrievedChunkCitationContext or ChunkRecord instances"
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_failure_messages(failures: Sequence[CitationValidationFailure]) -> str:
    return "; ".join(failure.message for failure in failures)


def _require_path(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def _validate_required_string(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


__all__ = [
    "CitationMarkerMatch",
    "CitationValidationFailure",
    "CitationValidationFailureCode",
    "CitationValidationOutcome",
    "CitationValidationResult",
    "CitationValidatorSmokeReport",
    "DEFAULT_CITATION_VALIDATOR_CONTEXT_FIXTURE_PATH",
    "RetrievedChunkCitationContext",
    "build_citation_record_map",
    "build_retrieved_chunk_map",
    "extract_citation_markers",
    "find_malformed_citation_markers",
    "load_retrieved_chunk_contexts",
    "render_citation_validator_smoke_report",
    "run_citation_validator_smoke",
    "validate_query_response_citations",
]
