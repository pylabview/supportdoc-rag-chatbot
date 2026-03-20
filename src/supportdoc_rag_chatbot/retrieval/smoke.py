from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DEVICE,
    create_local_embedder,
    load_chunk_records,
)
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_FAISS_INDEX_PATH,
    DEFAULT_FAISS_METADATA_PATH,
    DenseSearchResult,
    load_faiss_index_backend,
    read_index_metadata,
)

DEFAULT_RETRIEVAL_TOP_K = 5
DEFAULT_PREVIEW_CHARS = 200


@dataclass(slots=True)
class DenseRetrievalSmokeMatch:
    rank: int
    score: float
    chunk_id: str
    row_index: int
    doc_title: str
    section_path: str
    source_url: str
    source_path: str
    text_preview: str


@dataclass(slots=True)
class DenseRetrievalSmokeReport:
    query_text: str
    model_name: str
    top_k: int
    index_path: str
    index_metadata_path: str
    row_mapping_path: str
    chunks_path: str
    matches: list[DenseRetrievalSmokeMatch]


def run_dense_retrieval_smoke(
    *,
    query_text: str,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
    index_path: Path = DEFAULT_FAISS_INDEX_PATH,
    index_metadata_path: Path = DEFAULT_FAISS_METADATA_PATH,
    row_mapping_path: Path | None = None,
    chunks_path: Path | None = None,
    model_name: str | None = None,
    device: str = DEFAULT_DEVICE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
) -> DenseRetrievalSmokeReport:
    normalized_query = " ".join(query_text.split())
    if not normalized_query:
        raise ValueError("query text must not be empty")
    if top_k <= 0:
        raise ValueError("top_k must be > 0")
    if preview_chars <= 0:
        raise ValueError("preview_chars must be > 0")

    _require_path(index_metadata_path, label="Index metadata artifact")
    _require_path(index_path, label="FAISS index artifact")

    index_metadata = read_index_metadata(index_metadata_path)
    resolved_row_mapping_path = row_mapping_path or _metadata_path(
        index_metadata.row_mapping_path,
        label="row_mapping_path",
        source_path=index_metadata_path,
    )
    _require_path(resolved_row_mapping_path, label="Index row mapping artifact")

    resolved_chunks_path = chunks_path or _metadata_path(
        index_metadata.source_chunks_path,
        label="source_chunks_path",
        source_path=index_metadata_path,
    )
    _require_path(resolved_chunks_path, label="Chunks artifact")

    backend = load_faiss_index_backend(
        index_path=index_path,
        metadata_path=index_metadata_path,
        row_mapping_path=resolved_row_mapping_path,
    )
    chunks = load_chunk_records(resolved_chunks_path)
    if len(chunks) != backend.metadata.row_count:
        raise ValueError(
            "Chunk artifact row count does not match index metadata row count: "
            f"expected {backend.metadata.row_count}, got {len(chunks)}"
        )

    resolved_model_name = model_name or index_metadata.embedding_model_name
    embedder = create_local_embedder(
        model_name=resolved_model_name,
        device=device,
        batch_size=batch_size,
        normalize_embeddings=True,
    )
    query_vectors = embedder.embed_texts([normalized_query])
    if len(query_vectors) != 1:
        raise ValueError(f"Embedding backend returned {len(query_vectors)} rows for a single query")

    results = backend.search(query_vectors[0], top_k=top_k)
    matches = [
        _join_search_result(result=result, chunks=chunks, preview_chars=preview_chars)
        for result in results
    ]
    return DenseRetrievalSmokeReport(
        query_text=normalized_query,
        model_name=resolved_model_name,
        top_k=top_k,
        index_path=str(index_path),
        index_metadata_path=str(index_metadata_path),
        row_mapping_path=str(resolved_row_mapping_path),
        chunks_path=str(resolved_chunks_path),
        matches=matches,
    )


def render_dense_retrieval_smoke_report(report: DenseRetrievalSmokeReport) -> str:
    lines = [
        "Dense retrieval smoke test",
        f'query: "{report.query_text}"',
        f"model: {report.model_name}",
        f"top_k: {report.top_k}",
        f"index: {report.index_path}",
        f"index_metadata: {report.index_metadata_path}",
        f"row_mapping: {report.row_mapping_path}",
        f"chunks: {report.chunks_path}",
        "",
    ]

    if not report.matches:
        lines.append("No matches returned.")
        return "\n".join(lines)

    for match in report.matches:
        lines.extend(
            [
                f"[{match.rank}] score={match.score:.6f} chunk_id={match.chunk_id}",
                f"    title: {match.doc_title}",
                f"    section_path: {match.section_path}",
                f"    source_url: {match.source_url}",
                f"    preview: {match.text_preview}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def _join_search_result(
    *,
    result: DenseSearchResult,
    chunks: list[ChunkRecord],
    preview_chars: int,
) -> DenseRetrievalSmokeMatch:
    if result.row_index < 0 or result.row_index >= len(chunks):
        raise ValueError(
            f"Search result row index is out of range for chunks artifact: {result.row_index}"
        )

    chunk = chunks[result.row_index]
    if chunk.chunk_id != result.chunk_id:
        raise ValueError(
            "Search result chunk_id does not match the chunk artifact row mapping: "
            f"row {result.row_index} has {chunk.chunk_id!r}, result reported {result.chunk_id!r}"
        )

    return DenseRetrievalSmokeMatch(
        rank=result.rank,
        score=result.score,
        chunk_id=result.chunk_id,
        row_index=result.row_index,
        doc_title=chunk.doc_title,
        section_path=_format_section_path(chunk.section_path),
        source_url=chunk.source_url,
        source_path=chunk.source_path,
        text_preview=_preview_text(chunk.text, preview_chars=preview_chars),
    )


def _format_section_path(section_path: list[str]) -> str:
    if not section_path:
        return "(root)"
    return " > ".join(section_path)


def _preview_text(text: str, *, preview_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= preview_chars:
        return normalized
    return normalized[: max(1, preview_chars - 1)].rstrip() + "…"


def _metadata_path(raw_path: str | None, *, label: str, source_path: Path) -> Path:
    if not raw_path:
        raise ValueError(f"Missing {label} in artifact metadata: {source_path}")
    return Path(raw_path)


def _require_path(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
