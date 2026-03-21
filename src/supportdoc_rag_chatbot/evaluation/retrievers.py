from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHUNKS_PATH,
    DEFAULT_DEVICE,
    create_local_embedder,
    load_chunk_records,
)
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
    load_faiss_index_backend,
    read_index_metadata,
)

from .dev_qa import DevQAEntry
from .harness import RetrievalHit

DEFAULT_RRF_K = 60
DEFAULT_HYBRID_CANDIDATE_DEPTH = 20
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*")


@dataclass(slots=True)
class StaticEvaluationRetriever:
    name: str
    retriever_type: str = "static"
    hits_by_query_id: dict[str, list[RetrievalHit]] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def retrieve(self, entry: DevQAEntry, *, top_k: int) -> list[RetrievalHit]:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        return [_copy_hit(hit) for hit in self.hits_by_query_id.get(entry.query_id, [])[:top_k]]


@dataclass(slots=True)
class DenseFaissEvaluationRetriever:
    name: str = "dense-faiss"
    index_path: Path = DEFAULT_FAISS_INDEX_PATH
    index_metadata_path: Path = DEFAULT_FAISS_METADATA_PATH
    row_mapping_path: Path | None = None
    chunks_path: Path | None = None
    model_name: str | None = None
    device: str = DEFAULT_DEVICE
    batch_size: int = DEFAULT_BATCH_SIZE
    retriever_type: str = "dense"
    _backend: Any = field(init=False, default=None, repr=False)
    _chunks: list[ChunkRecord] = field(init=False, default_factory=list, repr=False)
    _embedder: Any = field(init=False, default=None, repr=False)

    @property
    def config(self) -> dict[str, Any]:
        return {
            "index_path": str(self.index_path),
            "index_metadata_path": str(self.index_metadata_path),
            "row_mapping_path": str(self.row_mapping_path) if self.row_mapping_path else None,
            "chunks_path": str(self.chunks_path) if self.chunks_path else None,
            "model_name": self.model_name,
            "device": self.device,
            "batch_size": self.batch_size,
        }

    def retrieve(self, entry: DevQAEntry, *, top_k: int) -> list[RetrievalHit]:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        self._ensure_loaded()

        query_text = " ".join(entry.question.split())
        if not query_text:
            return []

        query_vectors = self._embedder.embed_texts([query_text])
        if len(query_vectors) != 1:
            raise ValueError(f"Embedding backend returned {len(query_vectors)} rows for one query")

        hits: list[RetrievalHit] = []
        for result in self._backend.search(query_vectors[0], top_k=top_k):
            if result.row_index < 0 or result.row_index >= len(self._chunks):
                raise ValueError(f"Search result row index is out of range: {result.row_index}")
            chunk = self._chunks[result.row_index]
            if chunk.chunk_id != result.chunk_id:
                raise ValueError(
                    "Chunk row mapping does not match the FAISS result: "
                    f"row {result.row_index} has {chunk.chunk_id!r}, result reported {result.chunk_id!r}"
                )
            hits.append(
                RetrievalHit(
                    chunk_id=result.chunk_id,
                    score=result.score,
                    rank=result.rank,
                    doc_id=chunk.doc_id,
                    section_id=chunk.section_id,
                )
            )
        return hits

    def _ensure_loaded(self) -> None:
        if self._backend is not None and self._embedder is not None and self._chunks:
            return

        metadata = read_index_metadata(self.index_metadata_path)
        resolved_row_mapping_path = self.row_mapping_path or _required_metadata_path(
            metadata.row_mapping_path,
            label="row_mapping_path",
            source_path=self.index_metadata_path,
        )
        resolved_chunks_path = self.chunks_path or _required_metadata_path(
            metadata.source_chunks_path,
            label="source_chunks_path",
            source_path=self.index_metadata_path,
        )

        self._backend = load_faiss_index_backend(
            index_path=self.index_path,
            metadata_path=self.index_metadata_path,
            row_mapping_path=resolved_row_mapping_path,
        )
        self._chunks = load_chunk_records(resolved_chunks_path)
        if len(self._chunks) != self._backend.metadata.row_count:
            raise ValueError(
                "Chunk artifact row count does not match index metadata row count: "
                f"expected {self._backend.metadata.row_count}, got {len(self._chunks)}"
            )

        resolved_model_name = self.model_name or metadata.embedding_model_name
        self._embedder = create_local_embedder(
            model_name=resolved_model_name,
            device=self.device,
            batch_size=self.batch_size,
            normalize_embeddings=True,
        )


@dataclass(slots=True)
class BM25ChunkEvaluationRetriever:
    chunks_path: Path = DEFAULT_CHUNKS_PATH
    name: str = "bm25"
    retriever_type: str = "bm25"
    k1: float = 1.5
    b: float = 0.75
    _chunks: list[ChunkRecord] = field(init=False, default_factory=list, repr=False)
    _term_frequencies: list[Counter[str]] = field(init=False, default_factory=list, repr=False)
    _doc_frequencies: Counter[str] = field(init=False, default_factory=Counter, repr=False)
    _average_doc_length: float = field(init=False, default=0.0, repr=False)

    @property
    def config(self) -> dict[str, Any]:
        return {
            "chunks_path": str(self.chunks_path),
            "k1": self.k1,
            "b": self.b,
        }

    def retrieve(self, entry: DevQAEntry, *, top_k: int) -> list[RetrievalHit]:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        self._ensure_loaded()

        query_tokens = _tokenize(entry.question)
        if not query_tokens:
            return []

        query_terms = Counter(query_tokens)
        scored_hits: list[tuple[float, ChunkRecord]] = []
        document_count = len(self._chunks)
        for chunk, term_frequencies in zip(self._chunks, self._term_frequencies, strict=True):
            document_length = sum(term_frequencies.values())
            score = 0.0
            for term, query_term_frequency in query_terms.items():
                term_frequency = term_frequencies.get(term, 0)
                if term_frequency <= 0:
                    continue
                doc_frequency = self._doc_frequencies.get(term, 0)
                idf = math.log(
                    1.0 + ((document_count - doc_frequency + 0.5) / (doc_frequency + 0.5))
                )
                denominator = term_frequency + self.k1 * (
                    1.0 - self.b + self.b * (document_length / self._average_doc_length)
                )
                score += (
                    query_term_frequency * idf * ((term_frequency * (self.k1 + 1.0)) / denominator)
                )
            if score > 0.0:
                scored_hits.append((score, chunk))

        scored_hits.sort(key=lambda item: (-item[0], item[1].chunk_id))
        hits: list[RetrievalHit] = []
        for rank, (score, chunk) in enumerate(scored_hits[:top_k], start=1):
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    score=score,
                    rank=rank,
                    doc_id=chunk.doc_id,
                    section_id=chunk.section_id,
                )
            )
        return hits

    def _ensure_loaded(self) -> None:
        if self._chunks:
            return
        self._chunks = load_chunk_records(self.chunks_path)
        self._term_frequencies = [Counter(_tokenize(chunk.text)) for chunk in self._chunks]
        self._doc_frequencies = Counter()
        total_document_length = 0
        for term_frequencies in self._term_frequencies:
            total_document_length += sum(term_frequencies.values())
            for term in term_frequencies:
                self._doc_frequencies[term] += 1
        if not self._chunks or total_document_length <= 0:
            raise ValueError(f"Chunks artifact is empty or contains no tokens: {self.chunks_path}")
        self._average_doc_length = total_document_length / len(self._chunks)


@dataclass(slots=True)
class HybridRRFEvaluationRetriever:
    dense_retriever: Any
    lexical_retriever: Any
    name: str = "hybrid-rrf"
    retriever_type: str = "hybrid"
    rrf_k: int = DEFAULT_RRF_K
    candidate_depth: int = DEFAULT_HYBRID_CANDIDATE_DEPTH

    @property
    def config(self) -> dict[str, Any]:
        return {
            "rrf_k": self.rrf_k,
            "candidate_depth": self.candidate_depth,
            "dense_retriever": getattr(self.dense_retriever, "name", "dense"),
            "lexical_retriever": getattr(self.lexical_retriever, "name", "lexical"),
        }

    def retrieve(self, entry: DevQAEntry, *, top_k: int) -> list[RetrievalHit]:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self.rrf_k <= 0:
            raise ValueError("rrf_k must be > 0")
        if self.candidate_depth <= 0:
            raise ValueError("candidate_depth must be > 0")

        search_depth = max(top_k, self.candidate_depth)
        dense_hits = self.dense_retriever.retrieve(entry, top_k=search_depth)
        lexical_hits = self.lexical_retriever.retrieve(entry, top_k=search_depth)

        fused: dict[str, RetrievalHit] = {}
        fused_scores: dict[str, float] = {}
        provenance: dict[str, dict[str, int]] = {}

        for source_name, hits in (
            (getattr(self.dense_retriever, "name", "dense"), dense_hits),
            (getattr(self.lexical_retriever, "name", "lexical"), lexical_hits),
        ):
            for hit in hits:
                contribution = 1.0 / float(self.rrf_k + max(1, hit.rank))
                fused_scores[hit.chunk_id] = fused_scores.get(hit.chunk_id, 0.0) + contribution
                provenance.setdefault(hit.chunk_id, {})[f"{source_name}_rank"] = int(hit.rank)
                if hit.chunk_id not in fused:
                    fused[hit.chunk_id] = _copy_hit(hit)
                else:
                    existing = fused[hit.chunk_id]
                    if existing.doc_id is None and hit.doc_id is not None:
                        existing.doc_id = hit.doc_id
                    if existing.section_id is None and hit.section_id is not None:
                        existing.section_id = hit.section_id

        ranked_chunk_ids = sorted(
            fused_scores, key=lambda chunk_id: (-fused_scores[chunk_id], chunk_id)
        )
        hits: list[RetrievalHit] = []
        for rank, chunk_id in enumerate(ranked_chunk_ids[:top_k], start=1):
            base_hit = fused[chunk_id]
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    score=fused_scores[chunk_id],
                    rank=rank,
                    doc_id=base_hit.doc_id,
                    section_id=base_hit.section_id,
                    metadata=provenance.get(chunk_id, {}),
                )
            )
        return hits


def create_dev_qa_fixture_retriever(
    entries: list[DevQAEntry],
    *,
    fixture_name: str = "oracle",
    name: str | None = None,
    retriever_type: str = "fixture",
) -> StaticEvaluationRetriever:
    fixture = fixture_name.strip().lower()
    hits_by_query_id: dict[str, list[RetrievalHit]] = {}

    for entry in entries:
        if fixture == "empty":
            hits: list[RetrievalHit] = []
        elif fixture == "oracle":
            hits = _oracle_hits_for_entry(entry)
        elif fixture == "first-gold":
            hits = _oracle_hits_for_entry(entry)[:1]
        else:
            raise ValueError(
                f"Unsupported fixture_name {fixture_name!r}. Use oracle, first-gold, or empty."
            )
        hits_by_query_id[entry.query_id] = hits

    retriever_name = name or f"{retriever_type}-{fixture}"
    return StaticEvaluationRetriever(
        name=retriever_name,
        retriever_type=retriever_type,
        hits_by_query_id=hits_by_query_id,
        config={"fixture_name": fixture},
    )


def _oracle_hits_for_entry(entry: DevQAEntry) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    for rank, chunk_id in enumerate(entry.expected_chunk_ids, start=1):
        hits.append(
            RetrievalHit(
                chunk_id=chunk_id,
                score=1.0 / float(rank),
                rank=rank,
            )
        )
    if hits:
        return hits

    for rank, section_id in enumerate(entry.expected_section_ids, start=1):
        hits.append(
            RetrievalHit(
                chunk_id=f"section-only::{section_id}",
                score=1.0 / float(rank),
                rank=rank,
                section_id=section_id,
            )
        )
    return hits


def _copy_hit(hit: RetrievalHit) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=hit.chunk_id,
        score=hit.score,
        rank=hit.rank,
        doc_id=hit.doc_id,
        section_id=hit.section_id,
        metadata=dict(hit.metadata),
    )


def _required_metadata_path(raw_path: str | None, *, label: str, source_path: Path) -> Path:
    if not raw_path:
        raise ValueError(f"Missing {label} in artifact metadata: {source_path}")
    return Path(raw_path)


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text)]
