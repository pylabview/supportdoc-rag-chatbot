from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_FIXTURE_EMBEDDER_MODEL_NAME = "supportdoc-artifact-smoke-fixture-v1"


@dataclass(slots=True, frozen=True)
class FixtureEmbeddingMap:
    model_name: str
    vectors_by_text: dict[str, tuple[float, ...]]

    @property
    def vector_dimension(self) -> int:
        first_vector = next(iter(self.vectors_by_text.values()))
        return len(first_vector)


@dataclass(slots=True)
class FixtureDenseEmbedder:
    model_name: str
    vectors_by_text: dict[str, tuple[float, ...]]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        rows: list[list[float]] = []
        for text in texts:
            try:
                vector = self.vectors_by_text[text]
            except KeyError as exc:
                raise ValueError(
                    f"Fixture embedder mapping is missing a vector for text: {text!r}"
                ) from exc
            rows.append([float(value) for value in vector])
        return rows


def create_fixture_embedder(
    *,
    model_name: str = DEFAULT_FIXTURE_EMBEDDER_MODEL_NAME,
    vectors_by_text: Mapping[str, Sequence[float]],
) -> FixtureDenseEmbedder:
    fixture_map = FixtureEmbeddingMap(
        model_name=_validate_model_name(model_name),
        vectors_by_text=_normalize_vectors_by_text(vectors_by_text),
    )
    return FixtureDenseEmbedder(
        model_name=fixture_map.model_name,
        vectors_by_text=dict(fixture_map.vectors_by_text),
    )


def load_fixture_embedder(path: Path) -> FixtureDenseEmbedder:
    fixture_map = read_fixture_embedding_map(path)
    return FixtureDenseEmbedder(
        model_name=fixture_map.model_name,
        vectors_by_text=dict(fixture_map.vectors_by_text),
    )


def read_fixture_embedding_map(path: Path) -> FixtureEmbeddingMap:
    if not path.exists():
        raise FileNotFoundError(f"Fixture embedding map not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Fixture embedding map is not a file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Fixture embedding map is not valid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Fixture embedding map payload must be a JSON object")

    model_name = _validate_model_name(payload.get("model_name"))
    raw_vectors = payload.get("vectors_by_text")
    if not isinstance(raw_vectors, dict):
        raise ValueError("Fixture embedding map must define a vectors_by_text object")

    return FixtureEmbeddingMap(
        model_name=model_name,
        vectors_by_text=_normalize_vectors_by_text(raw_vectors),
    )


def write_fixture_embedding_map(
    path: Path,
    *,
    model_name: str = DEFAULT_FIXTURE_EMBEDDER_MODEL_NAME,
    vectors_by_text: Mapping[str, Sequence[float]],
) -> Path:
    fixture_map = FixtureEmbeddingMap(
        model_name=_validate_model_name(model_name),
        vectors_by_text=_normalize_vectors_by_text(vectors_by_text),
    )
    payload = {
        "model_name": fixture_map.model_name,
        "vectors_by_text": {
            text: [float(value) for value in vector]
            for text, vector in fixture_map.vectors_by_text.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _normalize_vectors_by_text(
    vectors_by_text: Mapping[str, Sequence[float]] | dict[str, Any],
) -> dict[str, tuple[float, ...]]:
    normalized: dict[str, tuple[float, ...]] = {}
    expected_dimension: int | None = None
    for raw_text, raw_vector in vectors_by_text.items():
        text = _validate_required_string(raw_text, field_name="text")
        if not isinstance(raw_vector, Sequence) or isinstance(raw_vector, (str, bytes, bytearray)):
            raise ValueError(
                f"Fixture embedding map vector for {text!r} must be an array of numbers"
            )
        vector = tuple(float(value) for value in raw_vector)
        if not vector:
            raise ValueError(f"Fixture embedding map vector for {text!r} must not be empty")
        if expected_dimension is None:
            expected_dimension = len(vector)
        elif len(vector) != expected_dimension:
            raise ValueError(
                "Fixture embedding map vectors must all share the same dimension: "
                f"expected {expected_dimension}, got {len(vector)} for {text!r}"
            )
        normalized[text] = vector

    if not normalized:
        raise ValueError("Fixture embedding map must define at least one text vector")
    return normalized


def _validate_required_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _validate_model_name(value: Any) -> str:
    return _validate_required_string(value, field_name="model_name")


__all__ = [
    "DEFAULT_FIXTURE_EMBEDDER_MODEL_NAME",
    "FixtureDenseEmbedder",
    "FixtureEmbeddingMap",
    "create_fixture_embedder",
    "load_fixture_embedder",
    "read_fixture_embedding_map",
    "write_fixture_embedding_map",
]
