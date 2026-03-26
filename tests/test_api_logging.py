from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from supportdoc_rag_chatbot.app.api import create_app
from supportdoc_rag_chatbot.config import BackendSettings
from supportdoc_rag_chatbot.logging_conf import (
    PACKAGE_LOGGER_NAME,
    REQUEST_ID_HEADER,
    JsonLogFormatter,
    configure_logging,
    log_event,
    request_id_context,
)

TEST_SETTINGS = BackendSettings(
    app_name="SupportDoc Logging Test API",
    environment="test",
    api_version="9.9.9",
    docs_url="/docs",
    redoc_url="/redoc",
    query_retrieval_mode="fixture",
    query_generation_mode="fixture",
)


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def capture_supportdoc_logs(*, level: int = logging.INFO) -> Iterator[list[logging.LogRecord]]:
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    handler = ListHandler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(level)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _event_records(records: list[logging.LogRecord], event_name: str) -> list[logging.LogRecord]:
    return [record for record in records if getattr(record, "event", None) == event_name]


def test_request_lifecycle_logs_include_request_id_status_code_and_duration() -> None:
    with capture_supportdoc_logs() as records:
        with TestClient(create_app(settings=TEST_SETTINGS)) as client:
            response = client.get("/healthz", headers={REQUEST_ID_HEADER: "req-healthz-001"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-healthz-001"

    started = _event_records(records, "api.request.started")
    completed = _event_records(records, "api.request.completed")

    assert len(started) == 1
    assert len(completed) == 1
    assert started[0].request_id == "req-healthz-001"
    assert started[0].path == "/healthz"
    assert started[0].route == "/healthz"
    assert completed[0].request_id == "req-healthz-001"
    assert completed[0].status_code == 200
    assert completed[0].route == "/healthz"
    assert completed[0].duration_ms >= 0


def test_supported_query_logs_citation_validation_outcome_with_request_correlation() -> None:
    with capture_supportdoc_logs() as records:
        with TestClient(create_app(settings=TEST_SETTINGS)) as client:
            response = client.post(
                "/query",
                json={"question": "What is a Pod?"},
                headers={REQUEST_ID_HEADER: "req-answer-001"},
            )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-answer-001"
    assert response.json()["refusal"]["is_refusal"] is False

    citation_events = _event_records(records, "query.citation_validation.completed")
    completion_events = _event_records(records, "query.completed")

    assert len(citation_events) == 1
    assert citation_events[0].request_id == "req-answer-001"
    assert citation_events[0].citation_validation_outcome == "valid"
    assert citation_events[0].failure_count == 0

    assert len(completion_events) == 1
    assert completion_events[0].request_id == "req-answer-001"
    assert completion_events[0].outcome == "answer"
    assert completion_events[0].retry_count == 0


def test_refusal_path_logs_reason_code_without_user_content() -> None:
    with capture_supportdoc_logs() as records:
        with TestClient(create_app(settings=TEST_SETTINGS)) as client:
            response = client.post(
                "/query",
                json={"question": "How do I reset my laptop BIOS?"},
                headers={REQUEST_ID_HEADER: "req-refusal-001"},
            )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-refusal-001"
    assert response.json()["refusal"]["reason_code"] == "no_relevant_docs"

    sufficiency_events = _event_records(records, "query.sufficiency.decided")
    refusal_events = _event_records(records, "query.refusal.returned")

    assert len(sufficiency_events) == 1
    assert sufficiency_events[0].request_id == "req-refusal-001"
    assert sufficiency_events[0].refusal_reason == "no_relevant_docs"
    assert sufficiency_events[0].sufficiency_action == "refuse_no_relevant_docs"

    assert len(refusal_events) == 1
    assert refusal_events[0].request_id == "req-refusal-001"
    assert refusal_events[0].refusal_reason == "no_relevant_docs"
    assert refusal_events[0].stage == "retrieval_sufficiency"
    assert not hasattr(refusal_events[0], "question")
    assert not hasattr(refusal_events[0], "system_prompt")
    assert not hasattr(refusal_events[0], "user_prompt")


def test_json_formatter_redacts_sensitive_fields_by_default() -> None:
    configure_logging(log_format="json")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("supportdoc_rag_chatbot.tests.redaction")
    logger.handlers = []
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        with request_id_context("req-redaction-001"):
            log_event(
                logger,
                "test.redaction",
                question="What is a Pod?",
                system_prompt="system prompt",
                user_prompt="user prompt",
                final_answer="answer text",
                refusal_reason="no_relevant_docs",
                retry_count=1,
            )
    finally:
        logger.removeHandler(handler)

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "test.redaction"
    assert payload["request_id"] == "req-redaction-001"
    assert payload["question"] == "[redacted]"
    assert payload["system_prompt"] == "[redacted]"
    assert payload["user_prompt"] == "[redacted]"
    assert payload["final_answer"] == "[redacted]"
    assert payload["refusal_reason"] == "no_relevant_docs"
    assert payload["retry_count"] == 1
