from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_TRUST_CONTRACT_DIR = Path("docs/contracts")
DEFAULT_TRUST_SCHEMA_PATH = DEFAULT_TRUST_CONTRACT_DIR / "query_response.schema.json"
DEFAULT_TRUST_ANSWER_FIXTURE_PATH = (
    DEFAULT_TRUST_CONTRACT_DIR / "query_response.answer.example.json"
)
DEFAULT_TRUST_REFUSAL_FIXTURE_PATH = (
    DEFAULT_TRUST_CONTRACT_DIR / "query_response.refusal.example.json"
)


class RefusalReasonCode(StrEnum):
    """Allowed refusal categories for user-visible trust-layer refusals."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_RELEVANT_DOCS = "no_relevant_docs"
    CITATION_VALIDATION_FAILED = "citation_validation_failed"
    OUT_OF_SCOPE = "out_of_scope"


class CitationRecord(BaseModel):
    """Pointer to one supporting span inside the approved corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    marker: str = Field(
        description="User-visible citation marker, for example [1] or [2].",
    )
    doc_id: str = Field(
        description="Stable source document identifier for the cited evidence.",
    )
    chunk_id: str = Field(
        description="Stable chunk identifier for the cited evidence span.",
    )
    start_offset: int = Field(
        ge=0,
        description="Inclusive start offset of the supporting span inside the chunk text.",
    )
    end_offset: int = Field(
        ge=0,
        description="Exclusive end offset of the supporting span inside the chunk text.",
    )

    @field_validator("marker", "doc_id", "chunk_id")
    @classmethod
    def _validate_required_string(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized

    @model_validator(mode="after")
    def _validate_offsets(self) -> "CitationRecord":
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class RefusalRecord(BaseModel):
    """Structured refusal payload attached to every query response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_refusal: bool = Field(
        description="Whether the response is an explicit refusal instead of a supported answer.",
    )
    reason_code: RefusalReasonCode | None = Field(
        description="Machine-readable refusal reason code, or null for supported answers.",
    )
    message: str | None = Field(
        description="User-visible refusal message, or null for supported answers.",
    )

    @field_validator("message")
    @classmethod
    def _validate_optional_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized

    @model_validator(mode="after")
    def _validate_refusal_fields(self) -> "RefusalRecord":
        if self.is_refusal:
            if self.reason_code is None:
                raise ValueError("reason_code is required when is_refusal is True")
            if self.message is None:
                raise ValueError("message is required when is_refusal is True")
            return self

        if self.reason_code is not None:
            raise ValueError("reason_code must be null when is_refusal is False")
        if self.message is not None:
            raise ValueError("message must be null when is_refusal is False")
        return self


class QueryResponse(BaseModel):
    """Canonical response contract shared by generation, validation, and API serialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    final_answer: str = Field(
        description=(
            "User-visible final answer text. For refusals this should be the refusal text shown "
            "to the user."
        ),
    )
    citations: list[CitationRecord] = Field(
        description="Supporting citation records for a grounded answer. Refusals must return an empty list.",
    )
    refusal: RefusalRecord = Field(
        description="Structured refusal state for the response.",
    )

    @field_validator("final_answer")
    @classmethod
    def _validate_final_answer(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("final_answer must not be blank")
        return normalized

    @model_validator(mode="after")
    def _validate_contract(self) -> "QueryResponse":
        if self.refusal.is_refusal:
            if self.citations:
                raise ValueError("citations must be empty when refusal.is_refusal is True")
            return self

        if not self.citations:
            raise ValueError(
                "citations must contain at least one record when refusal.is_refusal is False"
            )
        return self


@dataclass(slots=True)
class TrustSchemaSmokeReport:
    schema_path: str
    answer_fixture_path: str
    refusal_fixture_path: str
    answer_citation_count: int
    refusal_reason_code: str


def build_example_answer_response() -> QueryResponse:
    return QueryResponse(
        final_answer=(
            "A Pod is the smallest deployable unit in Kubernetes and can run one or more "
            "containers that share network and storage resources [1]."
        ),
        citations=[
            CitationRecord(
                marker="[1]",
                doc_id="content-en-docs-concepts-workloads-pods-pods",
                chunk_id="content-en-docs-concepts-workloads-pods-pods__chunk-0001",
                start_offset=0,
                end_offset=118,
            )
        ],
        refusal=RefusalRecord(
            is_refusal=False,
            reason_code=None,
            message=None,
        ),
    )


def build_example_refusal_response() -> QueryResponse:
    message = "I can’t answer that from the approved support corpus."
    return QueryResponse(
        final_answer=message,
        citations=[],
        refusal=RefusalRecord(
            is_refusal=True,
            reason_code=RefusalReasonCode.NO_RELEVANT_DOCS,
            message=message,
        ),
    )


def generate_query_response_json_schema() -> dict[str, Any]:
    """Return a deterministically ordered JSON Schema for QueryResponse."""

    schema = QueryResponse.model_json_schema()
    return _sorted_json_value(schema)


def export_query_response_schema(
    output_path: Path = DEFAULT_TRUST_SCHEMA_PATH,
) -> Path:
    """Write the canonical QueryResponse JSON Schema to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, generate_query_response_json_schema())
    return output_path


def run_trust_schema_smoke(
    *,
    schema_path: Path = DEFAULT_TRUST_SCHEMA_PATH,
    answer_fixture_path: Path = DEFAULT_TRUST_ANSWER_FIXTURE_PATH,
    refusal_fixture_path: Path = DEFAULT_TRUST_REFUSAL_FIXTURE_PATH,
) -> TrustSchemaSmokeReport:
    """Validate the checked-in schema and example payload fixtures together."""

    _require_path(schema_path, label="Trust schema")
    _require_path(answer_fixture_path, label="Trust answer fixture")
    _require_path(refusal_fixture_path, label="Trust refusal fixture")

    expected_schema = generate_query_response_json_schema()
    checked_in_schema = _read_json(schema_path)
    if checked_in_schema != expected_schema:
        raise ValueError(
            "Checked-in trust schema is out of date; regenerate it with export_query_response_schema()"
        )

    answer_response = QueryResponse.model_validate(_read_json(answer_fixture_path))
    if answer_response.refusal.is_refusal:
        raise ValueError("Answer fixture must be a supported answer, not a refusal")

    refusal_response = QueryResponse.model_validate(_read_json(refusal_fixture_path))
    if not refusal_response.refusal.is_refusal:
        raise ValueError("Refusal fixture must set refusal.is_refusal to True")

    return TrustSchemaSmokeReport(
        schema_path=str(schema_path),
        answer_fixture_path=str(answer_fixture_path),
        refusal_fixture_path=str(refusal_fixture_path),
        answer_citation_count=len(answer_response.citations),
        refusal_reason_code=str(refusal_response.refusal.reason_code),
    )


def render_trust_schema_smoke_report(report: TrustSchemaSmokeReport) -> str:
    return "\n".join(
        [
            "Trust schema smoke test",
            f"schema: {report.schema_path}",
            (
                "answer fixture: "
                f"{report.answer_fixture_path} (citations={report.answer_citation_count})"
            ),
            (
                "refusal fixture: "
                f"{report.refusal_fixture_path} (reason_code={report.refusal_reason_code})"
            ),
            "status: ok",
        ]
    )


def _sorted_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_json_value(item) for item in value]
    return value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _require_path(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


__all__ = [
    "CitationRecord",
    "DEFAULT_TRUST_ANSWER_FIXTURE_PATH",
    "DEFAULT_TRUST_CONTRACT_DIR",
    "DEFAULT_TRUST_REFUSAL_FIXTURE_PATH",
    "DEFAULT_TRUST_SCHEMA_PATH",
    "QueryResponse",
    "RefusalReasonCode",
    "RefusalRecord",
    "TrustSchemaSmokeReport",
    "build_example_answer_response",
    "build_example_refusal_response",
    "export_query_response_schema",
    "generate_query_response_json_schema",
    "render_trust_schema_smoke_report",
    "run_trust_schema_smoke",
]
