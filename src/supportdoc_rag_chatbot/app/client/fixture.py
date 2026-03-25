from __future__ import annotations

import json
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from supportdoc_rag_chatbot.app.schemas import (
    DEFAULT_TRUST_ANSWER_FIXTURE_PATH,
    DEFAULT_TRUST_REFUSAL_FIXTURE_PATH,
    QueryResponse,
)

from .types import (
    GenerationBackendMode,
    GenerationFailure,
    GenerationFailureCode,
    GenerationRequest,
    GenerationResult,
)

DEFAULT_FIXTURE_SUPPORTED_QUESTIONS = ("What is a Pod?",)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return _repo_root() / path


def _default_answer_fixture_path() -> Path:
    return _resolve_repo_path(DEFAULT_TRUST_ANSWER_FIXTURE_PATH)


def _default_refusal_fixture_path() -> Path:
    return _resolve_repo_path(DEFAULT_TRUST_REFUSAL_FIXTURE_PATH)


def _normalize_question(question: str) -> str:
    return question.strip().casefold()


def _normalize_answer_questions(answer_questions: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({_normalize_question(question) for question in answer_questions}))


@dataclass(slots=True)
class FixtureGenerationClient:
    """Deterministic generation backend backed by checked-in JSON fixtures."""

    answer_fixture_path: Path = field(default_factory=_default_answer_fixture_path)
    refusal_fixture_path: Path = field(default_factory=_default_refusal_fixture_path)
    answer_questions: Iterable[str] = DEFAULT_FIXTURE_SUPPORTED_QUESTIONS

    def __post_init__(self) -> None:
        self.answer_fixture_path = _resolve_repo_path(Path(self.answer_fixture_path))
        self.refusal_fixture_path = _resolve_repo_path(Path(self.refusal_fixture_path))
        self.answer_questions = _normalize_answer_questions(self.answer_questions)
        if not self.answer_questions:
            raise ValueError("answer_questions must contain at least one supported question")

    @property
    def backend_mode(self) -> GenerationBackendMode:
        return GenerationBackendMode.FIXTURE

    @property
    def backend_name(self) -> str:
        return self.backend_mode.value

    def generate(self, request: GenerationRequest) -> GenerationResult:
        fixture_path = self._select_fixture_path(request)
        return _load_query_response_fixture(fixture_path, backend_name=self.backend_name)

    def close(self) -> None:
        return None

    def _select_fixture_path(self, request: GenerationRequest) -> Path:
        normalized_question = _normalize_question(request.question)
        if normalized_question in self.answer_questions:
            return self.answer_fixture_path
        return self.refusal_fixture_path


def _load_query_response_fixture(path: Path, *, backend_name: str) -> GenerationResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return GenerationResult.success(QueryResponse.model_validate(payload))
    except (JSONDecodeError, ValidationError) as exc:
        return GenerationResult.from_failure(
            GenerationFailure(
                code=GenerationFailureCode.PARSE_ERROR,
                message=f"Failed to parse generation fixture: {path}",
                backend_name=backend_name,
                retryable=False,
                details={"error": str(exc), "path": str(path)},
            )
        )
    except OSError as exc:
        return GenerationResult.from_failure(
            GenerationFailure(
                code=GenerationFailureCode.BACKEND_ERROR,
                message=f"Failed to load generation fixture: {path}",
                backend_name=backend_name,
                retryable=False,
                details={"error": str(exc), "path": str(path)},
            )
        )


__all__ = [
    "DEFAULT_FIXTURE_SUPPORTED_QUESTIONS",
    "FixtureGenerationClient",
]
