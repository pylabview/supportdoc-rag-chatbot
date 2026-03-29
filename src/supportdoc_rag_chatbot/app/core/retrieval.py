from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from supportdoc_rag_chatbot.app.services import RetrievedChunkCitationContext, RetrievedContextChunk
from supportdoc_rag_chatbot.app.services.policy_types import RetrievalScoreNormalization
from supportdoc_rag_chatbot.evaluation import RetrievalHit
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import DEFAULT_BATCH_SIZE, DEFAULT_DEVICE
from supportdoc_rag_chatbot.retrieval.embeddings.fixture import load_fixture_embedder
from supportdoc_rag_chatbot.retrieval.embeddings.job import load_chunk_records
from supportdoc_rag_chatbot.retrieval.embeddings.models import DenseEmbedder, create_local_embedder
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
    DEFAULT_FAISS_ROW_MAPPING_PATH,
    FaissDenseIndexBackend,
    load_faiss_index_backend,
    read_index_metadata,
)

from .errors import QueryPipelineConfigurationError, QueryPipelineRuntimeError

_DEFAULT_FIXTURE_SECTION_PATH = ("Concepts", "Workloads", "Pods")
_DEFAULT_FIXTURE_SOURCE_PATH = "content/en/docs/concepts/workloads/pods/pods.md"
_DEFAULT_FIXTURE_SOURCE_URL = "https://kubernetes.io/docs/concepts/workloads/pods/"
_DEFAULT_FIXTURE_POD_DOC_ID = "content-en-docs-concepts-workloads-pods-pods"


class RetrievalBackendMode(StrEnum):
    """Supported backend retrieval modes for query orchestration."""

    FIXTURE = "fixture"
    ARTIFACT = "artifact"


_DEFAULT_ARTIFACT_EMBEDDER_MODE = "local"
_VALID_ARTIFACT_EMBEDDER_MODES = {"local", "fixture"}


@dataclass(slots=True, frozen=True)
class RetrievedEvidenceChunk:
    """Minimal retrieval result shape consumed by prompting and validation."""

    doc_id: str
    chunk_id: str
    text: str
    score: float
    rank: int
    section_id: str | None = None
    section_path: tuple[str, ...] = ()
    source_path: str | None = None
    source_url: str | None = None
    start_offset: int = 0
    end_offset: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "doc_id",
            _validate_required_string(self.doc_id, field_name="doc_id"),
        )
        object.__setattr__(
            self,
            "chunk_id",
            _validate_required_string(self.chunk_id, field_name="chunk_id"),
        )
        object.__setattr__(self, "text", _validate_required_string(self.text, field_name="text"))
        object.__setattr__(self, "score", _validate_unit_interval_score(self.score))
        if self.rank <= 0:
            raise ValueError("rank must be > 0")
        object.__setattr__(self, "section_id", _normalize_optional_string(self.section_id))
        normalized_section_path = tuple(part.strip() for part in self.section_path if part.strip())
        object.__setattr__(self, "section_path", normalized_section_path)
        object.__setattr__(self, "source_path", _normalize_optional_string(self.source_path))
        object.__setattr__(self, "source_url", _normalize_optional_string(self.source_url))
        if self.start_offset < 0:
            raise ValueError("start_offset must be >= 0")
        resolved_end_offset = len(self.text) if self.end_offset is None else int(self.end_offset)
        if resolved_end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        object.__setattr__(self, "end_offset", resolved_end_offset)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_chunk_record(
        cls,
        chunk: ChunkRecord,
        *,
        score: float,
        rank: int,
        metadata: dict[str, Any] | None = None,
    ) -> "RetrievedEvidenceChunk":
        return cls(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            score=score,
            rank=rank,
            section_id=chunk.section_id,
            section_path=tuple(chunk.section_path),
            source_path=chunk.source_path,
            source_url=chunk.source_url,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            metadata=(dict(metadata) if metadata is not None else {}),
        )

    def to_retrieval_hit(self) -> RetrievalHit:
        return RetrievalHit(
            chunk_id=self.chunk_id,
            score=self.score,
            rank=self.rank,
            doc_id=self.doc_id,
            section_id=self.section_id,
            metadata=dict(self.metadata),
        )

    def to_prompt_chunk(self) -> RetrievedContextChunk:
        return RetrievedContextChunk(
            doc_id=self.doc_id,
            chunk_id=self.chunk_id,
            text=self.text,
            section_path=self.section_path,
            source_path=self.source_path,
            source_url=self.source_url,
        )

    def to_citation_context(self) -> RetrievedChunkCitationContext:
        assert self.end_offset is not None
        return RetrievedChunkCitationContext(
            doc_id=self.doc_id,
            chunk_id=self.chunk_id,
            start_offset=self.start_offset,
            end_offset=self.end_offset,
            text=self.text,
        )


@dataclass(slots=True, frozen=True)
class RetrievedEvidenceBundle:
    """Request-scoped retrieval evidence emitted by the backend adapter."""

    chunks: tuple[RetrievedEvidenceChunk, ...]
    retriever_name: str
    retriever_type: str
    config: dict[str, Any] = field(default_factory=dict)
    score_normalization: RetrievalScoreNormalization = RetrievalScoreNormalization.UNIT_INTERVAL

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "retriever_name",
            _validate_required_string(self.retriever_name, field_name="retriever_name"),
        )
        object.__setattr__(
            self,
            "retriever_type",
            _validate_required_string(self.retriever_type, field_name="retriever_type"),
        )
        object.__setattr__(self, "config", dict(self.config))

    def to_retrieval_hits(self) -> list[RetrievalHit]:
        return [chunk.to_retrieval_hit() for chunk in self.chunks]

    def to_prompt_chunks(self) -> list[RetrievedContextChunk]:
        return [chunk.to_prompt_chunk() for chunk in self.chunks]

    def to_citation_contexts(self) -> list[RetrievedChunkCitationContext]:
        return [chunk.to_citation_context() for chunk in self.chunks]


def _normalize_artifact_embedder_mode(mode: str) -> str:
    normalized = _validate_required_string(mode, field_name="embedder_mode").casefold()
    if normalized not in _VALID_ARTIFACT_EMBEDDER_MODES:
        raise ValueError(
            "embedder_mode must be one of: " + ", ".join(sorted(_VALID_ARTIFACT_EMBEDDER_MODES))
        )
    return normalized


def _normalize_question(question: str) -> str:
    return _validate_required_string(question, field_name="question").casefold()


def _normalize_ranked_chunks(
    chunks: Sequence[RetrievedEvidenceChunk],
) -> tuple[RetrievedEvidenceChunk, ...]:
    sorted_chunks = sorted(chunks, key=lambda chunk: (chunk.rank, chunk.chunk_id))
    return _rerank_chunks(sorted_chunks)


def _rerank_chunks(chunks: Sequence[RetrievedEvidenceChunk]) -> tuple[RetrievedEvidenceChunk, ...]:
    reranked: list[RetrievedEvidenceChunk] = []
    for rank, chunk in enumerate(chunks, start=1):
        reranked.append(
            RetrievedEvidenceChunk(
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                score=chunk.score,
                rank=rank,
                section_id=chunk.section_id,
                section_path=chunk.section_path,
                source_path=chunk.source_path,
                source_url=chunk.source_url,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                metadata=chunk.metadata,
            )
        )
    return tuple(reranked)


def _normalize_cosine_similarity(score: float) -> float:
    if not isfinite(score):
        raise QueryPipelineRuntimeError("Artifact retrieval backend returned a non-finite score.")
    normalized = (float(score) + 1.0) / 2.0
    if normalized < 0.0:
        return 0.0
    if normalized > 1.0:
        return 1.0
    return normalized


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


def _validate_unit_interval_score(value: float) -> float:
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError("score must be a finite float")
    if not 0.0 <= normalized <= 1.0:
        raise ValueError("score must be between 0.0 and 1.0")
    return normalized


def _require_file(path: Path, *, label: str) -> None:
    if not path.exists():
        raise QueryPipelineConfigurationError(f"{label} not found: {path}")
    if not path.is_file():
        raise QueryPipelineConfigurationError(f"{label} is not a file: {path}")


_DEFAULT_FIXTURE_CONTEXT = (
    RetrievedEvidenceChunk(
        doc_id=_DEFAULT_FIXTURE_POD_DOC_ID,
        chunk_id=f"{_DEFAULT_FIXTURE_POD_DOC_ID}__chunk-0001",
        text=(
            "A Pod is the smallest deployable unit in Kubernetes and can run one or more "
            "containers that share network and storage resources."
        ),
        score=0.97,
        rank=1,
        section_id=f"{_DEFAULT_FIXTURE_POD_DOC_ID}__section-0001",
        section_path=_DEFAULT_FIXTURE_SECTION_PATH,
        source_path=_DEFAULT_FIXTURE_SOURCE_PATH,
        source_url=_DEFAULT_FIXTURE_SOURCE_URL,
        start_offset=0,
        end_offset=128,
    ),
    RetrievedEvidenceChunk(
        doc_id=_DEFAULT_FIXTURE_POD_DOC_ID,
        chunk_id=f"{_DEFAULT_FIXTURE_POD_DOC_ID}__chunk-0002",
        text=(
            "Pods can also group closely related containers so they share the same network "
            "identity and can coordinate storage resources."
        ),
        score=0.83,
        rank=2,
        section_id=f"{_DEFAULT_FIXTURE_POD_DOC_ID}__section-0001",
        section_path=_DEFAULT_FIXTURE_SECTION_PATH,
        source_path=_DEFAULT_FIXTURE_SOURCE_PATH,
        source_url=_DEFAULT_FIXTURE_SOURCE_URL,
        start_offset=0,
    ),
)
_DEFAULT_FIXTURE_QUESTION_MAP = {"what is a pod?": _DEFAULT_FIXTURE_CONTEXT}


@runtime_checkable
class QueryRetriever(Protocol):
    """Backend-agnostic retrieval adapter used by the API orchestration service."""

    backend_mode: RetrievalBackendMode
    name: str
    retriever_type: str

    @property
    def config(self) -> dict[str, Any]:
        """Return a deterministic retriever configuration payload."""

    def retrieve(self, question: str, *, top_k: int) -> RetrievedEvidenceBundle:
        """Return request-scoped retrieved evidence for one user question."""


@dataclass(slots=True)
class FixtureQueryRetriever:
    """Deterministic retrieval adapter for repo-only local smoke testing."""

    hits_by_question: Mapping[str, Sequence[RetrievedEvidenceChunk]] | None = None
    name: str = "fixture-retriever"
    retriever_type: str = "fixture"

    def __post_init__(self) -> None:
        normalized_hits: dict[str, tuple[RetrievedEvidenceChunk, ...]] = {}
        source = self.hits_by_question or _DEFAULT_FIXTURE_QUESTION_MAP
        for question, chunks in source.items():
            normalized_hits[_normalize_question(question)] = _normalize_ranked_chunks(chunks)
        self.hits_by_question = normalized_hits

    @property
    def backend_mode(self) -> RetrievalBackendMode:
        return RetrievalBackendMode.FIXTURE

    @property
    def config(self) -> dict[str, Any]:
        return {
            "fixture_questions": sorted(self.hits_by_question),
            "score_normalization": RetrievalScoreNormalization.UNIT_INTERVAL.value,
        }

    def retrieve(self, question: str, *, top_k: int) -> RetrievedEvidenceBundle:
        normalized_question = _normalize_question(question)
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        chunks = tuple(self.hits_by_question.get(normalized_question, ()))
        selected = _rerank_chunks(chunks[:top_k])
        return RetrievedEvidenceBundle(
            chunks=selected,
            retriever_name=self.name,
            retriever_type=self.retriever_type,
            config=self.config,
        )


@dataclass(slots=True)
class ArtifactDenseQueryRetriever:
    """Artifact-backed dense retrieval adapter for the backend query pipeline."""

    index_path: Path | None = DEFAULT_FAISS_INDEX_PATH
    metadata_path: Path | None = DEFAULT_FAISS_METADATA_PATH
    row_mapping_path: Path | None = DEFAULT_FAISS_ROW_MAPPING_PATH
    chunks_path: Path | None = None
    model_name: str | None = None
    device: str = DEFAULT_DEVICE
    batch_size: int = DEFAULT_BATCH_SIZE
    embedder_mode: str = _DEFAULT_ARTIFACT_EMBEDDER_MODE
    embedder_fixture_path: Path | None = None
    name: str = "dense-artifact-retriever"
    retriever_type: str = "dense-artifact"
    embedder: DenseEmbedder | None = None
    backend: FaissDenseIndexBackend | None = None
    _resolved_backend: FaissDenseIndexBackend | None = field(default=None, init=False, repr=False)
    _resolved_embedder: DenseEmbedder | None = field(default=None, init=False, repr=False)
    _chunk_map: dict[str, ChunkRecord] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.index_path = Path(self.index_path or DEFAULT_FAISS_INDEX_PATH)
        self.metadata_path = Path(self.metadata_path or DEFAULT_FAISS_METADATA_PATH)
        self.row_mapping_path = Path(self.row_mapping_path or DEFAULT_FAISS_ROW_MAPPING_PATH)
        self.chunks_path = Path(self.chunks_path) if self.chunks_path is not None else None
        self.embedder_fixture_path = (
            Path(self.embedder_fixture_path) if self.embedder_fixture_path is not None else None
        )
        self.embedder_mode = _normalize_artifact_embedder_mode(self.embedder_mode)

    @property
    def backend_mode(self) -> RetrievalBackendMode:
        return RetrievalBackendMode.ARTIFACT

    @property
    def config(self) -> dict[str, Any]:
        return {
            "index_path": str(self.index_path),
            "metadata_path": str(self.metadata_path),
            "row_mapping_path": (str(self.row_mapping_path) if self.row_mapping_path else None),
            "chunks_path": (str(self.chunks_path) if self.chunks_path else None),
            "model_name": self.model_name,
            "device": self.device,
            "batch_size": self.batch_size,
            "embedder_mode": self.embedder_mode,
            "embedder_fixture_path": (
                str(self.embedder_fixture_path) if self.embedder_fixture_path else None
            ),
            "score_normalization": RetrievalScoreNormalization.UNIT_INTERVAL.value,
        }

    def retrieve(self, question: str, *, top_k: int) -> RetrievedEvidenceBundle:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        normalized_question = _validate_required_string(question, field_name="question")
        backend = self._ensure_backend_loaded()
        embedder = self._ensure_embedder_loaded(backend)
        vectors = embedder.embed_texts([normalized_question])
        if len(vectors) != 1:
            raise QueryPipelineRuntimeError(
                "Artifact retrieval backend did not produce exactly one query embedding."
            )

        raw_results = backend.search(vectors[0], top_k=top_k)
        chunks: list[RetrievedEvidenceChunk] = []
        for rank, raw_result in enumerate(raw_results, start=1):
            chunk = self._chunk_map.get(raw_result.chunk_id)
            if chunk is None:
                raise QueryPipelineRuntimeError(
                    "Artifact retrieval backend returned a chunk_id that is missing from the "
                    f"resolved chunks artifact: {raw_result.chunk_id}"
                )
            chunks.append(
                RetrievedEvidenceChunk.from_chunk_record(
                    chunk,
                    score=_normalize_cosine_similarity(raw_result.score),
                    rank=rank,
                    metadata={
                        "raw_score": float(raw_result.score),
                        "row_index": raw_result.row_index,
                        "source_chunks_path": raw_result.source_chunks_path,
                    },
                )
            )

        return RetrievedEvidenceBundle(
            chunks=tuple(chunks),
            retriever_name=self.name,
            retriever_type=self.retriever_type,
            config=self.config,
        )

    def _ensure_backend_loaded(self) -> FaissDenseIndexBackend:
        if self._resolved_backend is not None:
            return self._resolved_backend

        metadata_path = Path(self.metadata_path)
        index_path = Path(self.index_path)
        _require_file(metadata_path, label="artifact retrieval metadata")
        _require_file(index_path, label="artifact retrieval index")

        metadata = read_index_metadata(metadata_path)
        resolved_row_mapping_path = self.row_mapping_path
        if resolved_row_mapping_path is None:
            if not metadata.row_mapping_path:
                raise QueryPipelineConfigurationError(
                    "Artifact retrieval mode requires a FAISS row-mapping artifact path."
                )
            resolved_row_mapping_path = Path(metadata.row_mapping_path)
        _require_file(Path(resolved_row_mapping_path), label="artifact retrieval row mapping")

        resolved_chunks_path = self.chunks_path or Path(metadata.source_chunks_path)
        _require_file(Path(resolved_chunks_path), label="artifact retrieval chunks")

        try:
            backend = self.backend or load_faiss_index_backend(
                index_path=index_path,
                metadata_path=metadata_path,
                row_mapping_path=Path(resolved_row_mapping_path),
            )
        except FileNotFoundError as exc:
            raise QueryPipelineConfigurationError(str(exc)) from exc
        except ValueError as exc:
            raise QueryPipelineConfigurationError(
                f"Artifact retrieval metadata is invalid: {exc}"
            ) from exc
        except RuntimeError as exc:
            raise QueryPipelineRuntimeError(
                f"Artifact retrieval backend could not be loaded: {exc}"
            ) from exc

        try:
            chunks = load_chunk_records(Path(resolved_chunks_path))
        except FileNotFoundError as exc:
            raise QueryPipelineConfigurationError(str(exc)) from exc
        except ValueError as exc:
            raise QueryPipelineConfigurationError(
                f"Artifact retrieval chunks are invalid: {exc}"
            ) from exc

        self._resolved_backend = backend
        self._chunk_map = {chunk.chunk_id: chunk for chunk in chunks}
        return backend

    def _ensure_embedder_loaded(self, backend: FaissDenseIndexBackend) -> DenseEmbedder:
        if self._resolved_embedder is not None:
            return self._resolved_embedder
        if self.embedder is not None:
            self._resolved_embedder = self.embedder
            return self._resolved_embedder

        if self.embedder_mode == "fixture":
            if self.embedder_fixture_path is None:
                raise QueryPipelineConfigurationError(
                    "Artifact retrieval fixture embedder mode requires an embedder fixture path."
                )
            try:
                self._resolved_embedder = load_fixture_embedder(Path(self.embedder_fixture_path))
            except FileNotFoundError as exc:
                raise QueryPipelineConfigurationError(str(exc)) from exc
            except ValueError as exc:
                raise QueryPipelineConfigurationError(
                    f"Artifact retrieval fixture embedder is invalid: {exc}"
                ) from exc
            return self._resolved_embedder

        try:
            self._resolved_embedder = create_local_embedder(
                model_name=(self.model_name or backend.metadata.embedding_model_name),
                device=self.device,
                batch_size=self.batch_size,
            )
        except RuntimeError as exc:
            raise QueryPipelineRuntimeError(
                f"Artifact retrieval embedder could not be created: {exc}"
            ) from exc
        return self._resolved_embedder


def create_query_retriever(
    *,
    mode: RetrievalBackendMode | str,
    **kwargs: Any,
) -> QueryRetriever:
    """Create the canonical query retriever for the requested backend mode."""

    resolved_mode = RetrievalBackendMode(mode)
    if resolved_mode is RetrievalBackendMode.FIXTURE:
        return FixtureQueryRetriever(**kwargs)
    return ArtifactDenseQueryRetriever(**kwargs)


__all__ = [
    "ArtifactDenseQueryRetriever",
    "FixtureQueryRetriever",
    "QueryRetriever",
    "RetrievalBackendMode",
    "RetrievedEvidenceBundle",
    "RetrievedEvidenceChunk",
    "create_query_retriever",
]
