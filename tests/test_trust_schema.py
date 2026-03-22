from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from supportdoc_rag_chatbot.app.schemas import (
    QueryResponse,
    build_example_answer_response,
    build_example_refusal_response,
    export_query_response_schema,
    generate_query_response_json_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs/contracts/query_response.schema.json"
ANSWER_FIXTURE_PATH = REPO_ROOT / "docs/contracts/query_response.answer.example.json"
REFUSAL_FIXTURE_PATH = REPO_ROOT / "docs/contracts/query_response.refusal.example.json"


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_query_response_schema_writes_deterministic_schema(tmp_path: Path) -> None:
    output_path = tmp_path / "query_response.schema.json"

    returned_path = export_query_response_schema(output_path)

    assert returned_path == output_path
    assert _read_json(output_path) == generate_query_response_json_schema()
    assert _read_json(output_path) == _read_json(SCHEMA_PATH)


def test_checked_in_answer_fixture_matches_example_builder() -> None:
    assert _read_json(ANSWER_FIXTURE_PATH) == build_example_answer_response().model_dump(
        mode="json"
    )


def test_checked_in_refusal_fixture_matches_example_builder() -> None:
    assert _read_json(REFUSAL_FIXTURE_PATH) == build_example_refusal_response().model_dump(
        mode="json"
    )


def test_query_response_accepts_checked_in_answer_fixture() -> None:
    response = QueryResponse.model_validate(_read_json(ANSWER_FIXTURE_PATH))

    assert response.refusal.is_refusal is False
    assert len(response.citations) == 1
    assert response.citations[0].marker == "[1]"


def test_query_response_accepts_checked_in_refusal_fixture() -> None:
    response = QueryResponse.model_validate(_read_json(REFUSAL_FIXTURE_PATH))

    assert response.refusal.is_refusal is True
    assert response.refusal.reason_code == "no_relevant_docs"
    assert response.citations == []


def test_supported_answer_requires_at_least_one_citation() -> None:
    payload = {
        "final_answer": "Pods run containers.",
        "citations": [],
        "refusal": {
            "is_refusal": False,
            "reason_code": None,
            "message": None,
        },
    }

    with pytest.raises(
        ValidationError,
        match="citations must contain at least one record when refusal.is_refusal is False",
    ):
        QueryResponse.model_validate(payload)


def test_refusal_requires_empty_citation_list() -> None:
    payload = {
        "final_answer": "I can’t answer that from the approved support corpus.",
        "citations": [
            {
                "marker": "[1]",
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "start_offset": 0,
                "end_offset": 5,
            }
        ],
        "refusal": {
            "is_refusal": True,
            "reason_code": "no_relevant_docs",
            "message": "I can’t answer that from the approved support corpus.",
        },
    }

    with pytest.raises(
        ValidationError,
        match="citations must be empty when refusal.is_refusal is True",
    ):
        QueryResponse.model_validate(payload)


def test_refusal_requires_reason_code_and_message() -> None:
    payload = {
        "final_answer": "I can’t answer that from the approved support corpus.",
        "citations": [],
        "refusal": {
            "is_refusal": True,
            "reason_code": None,
            "message": None,
        },
    }

    with pytest.raises(ValidationError, match="reason_code is required when is_refusal is True"):
        QueryResponse.model_validate(payload)


def test_refusal_reason_code_is_restricted_to_allowed_values() -> None:
    payload = {
        "final_answer": "I can’t answer that from the approved support corpus.",
        "citations": [],
        "refusal": {
            "is_refusal": True,
            "reason_code": "made_up_reason",
            "message": "I can’t answer that from the approved support corpus.",
        },
    }

    with pytest.raises(ValidationError, match="insufficient_evidence"):
        QueryResponse.model_validate(payload)


def test_citation_offsets_must_increase() -> None:
    payload = {
        "final_answer": "Pods run containers.",
        "citations": [
            {
                "marker": "[1]",
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "start_offset": 10,
                "end_offset": 10,
            }
        ],
        "refusal": {
            "is_refusal": False,
            "reason_code": None,
            "message": None,
        },
    }

    with pytest.raises(ValidationError, match="end_offset must be greater than start_offset"):
        QueryResponse.model_validate(payload)
