from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import (
    EmbeddingMetadata,
    read_embedding_metadata,
    read_vector_rows,
)
from supportdoc_rag_chatbot.retrieval.embeddings.job import load_chunk_records

DEFAULT_PGVECTOR_SCHEMA_NAME = "supportdoc_rag"
DEFAULT_PGVECTOR_RUNTIME_ID = "default"
DEFAULT_PGVECTOR_DISTANCE_METRIC = "cosine"
DEFAULT_PGVECTOR_CHUNKS_TABLE = "chunks"
DEFAULT_PGVECTOR_EMBEDDINGS_TABLE = "chunk_embeddings"
DEFAULT_PGVECTOR_METADATA_TABLE = "runtime_metadata"

ConnectionFactory = Callable[..., psycopg.Connection]


@dataclass(slots=True, frozen=True)
class PgvectorRuntimeMetadata:
    runtime_id: str
    artifact_version: str
    snapshot_id: str | None
    embedding_model_name: str
    vector_dimension: int
    row_count: int
    source_chunks_path: str
    embedding_metadata_path: str
    vectors_path: str
    distance_metric: str = DEFAULT_PGVECTOR_DISTANCE_METRIC

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PgvectorRuntimeMetadata":
        return cls(
            runtime_id=str(payload["runtime_id"]),
            artifact_version=str(payload["artifact_version"]),
            snapshot_id=(str(payload["snapshot_id"]) if payload.get("snapshot_id") else None),
            embedding_model_name=str(payload["embedding_model_name"]),
            vector_dimension=int(payload["vector_dimension"]),
            row_count=int(payload["row_count"]),
            source_chunks_path=str(payload["source_chunks_path"]),
            embedding_metadata_path=str(payload["embedding_metadata_path"]),
            vectors_path=str(payload["vectors_path"]),
            distance_metric=str(payload.get("distance_metric", DEFAULT_PGVECTOR_DISTANCE_METRIC)),
        )

    @classmethod
    def from_embedding_metadata(
        cls,
        metadata: EmbeddingMetadata,
        *,
        runtime_id: str = DEFAULT_PGVECTOR_RUNTIME_ID,
        distance_metric: str = DEFAULT_PGVECTOR_DISTANCE_METRIC,
        embedding_metadata_path: Path,
    ) -> "PgvectorRuntimeMetadata":
        return cls(
            runtime_id=runtime_id,
            artifact_version=metadata.artifact_version,
            snapshot_id=metadata.snapshot_id,
            embedding_model_name=metadata.embedding_model_name,
            vector_dimension=metadata.vector_dimension,
            row_count=metadata.row_count,
            source_chunks_path=metadata.source_chunks_path,
            embedding_metadata_path=str(embedding_metadata_path),
            vectors_path=(metadata.vectors_path or ""),
            distance_metric=distance_metric,
        )

    def to_insert_mapping(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "artifact_version": self.artifact_version,
            "snapshot_id": self.snapshot_id,
            "embedding_model_name": self.embedding_model_name,
            "vector_dimension": self.vector_dimension,
            "row_count": self.row_count,
            "source_chunks_path": self.source_chunks_path,
            "embedding_metadata_path": self.embedding_metadata_path,
            "vectors_path": self.vectors_path,
            "distance_metric": self.distance_metric,
        }


@dataclass(slots=True, frozen=True)
class PgvectorPromotionReport:
    schema_name: str
    runtime_id: str
    row_count: int
    vector_dimension: int
    embedding_model_name: str
    source_chunks_path: str
    embedding_metadata_path: str


@dataclass(slots=True, frozen=True)
class PgvectorSearchMatch:
    chunk: ChunkRecord
    raw_score: float


def validate_pgvector_schema_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("schema_name must not be blank")
    if not normalized.replace("_", "a").isalnum() or normalized[0].isdigit():
        raise ValueError(
            "schema_name must start with a letter or underscore and contain only letters, numbers, and underscores"
        )
    return normalized


class PgvectorDenseIndexBackend:
    """Minimal PostgreSQL + pgvector search backend for backend runtime retrieval."""

    def __init__(
        self,
        *,
        dsn: str,
        schema_name: str = DEFAULT_PGVECTOR_SCHEMA_NAME,
        runtime_id: str = DEFAULT_PGVECTOR_RUNTIME_ID,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.dsn = _validate_required_string(dsn, field_name="dsn")
        self.schema_name = validate_pgvector_schema_name(schema_name)
        self.runtime_id = _validate_required_string(runtime_id, field_name="runtime_id")
        self._connection_factory = connection_factory or psycopg.connect
        self._runtime_metadata: PgvectorRuntimeMetadata | None = None

    @property
    def runtime_metadata(self) -> PgvectorRuntimeMetadata:
        if self._runtime_metadata is None:
            self._runtime_metadata = load_pgvector_runtime_metadata(
                dsn=self.dsn,
                schema_name=self.schema_name,
                runtime_id=self.runtime_id,
                connection_factory=self._connection_factory,
            )
        return self._runtime_metadata

    def search(self, query_vector: Sequence[float], *, top_k: int = 5) -> list[PgvectorSearchMatch]:
        normalized_vector = [float(value) for value in query_vector]
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        if not normalized_vector:
            raise ValueError("query_vector must not be empty")

        runtime_metadata = self.runtime_metadata
        if len(normalized_vector) != runtime_metadata.vector_dimension:
            raise ValueError(
                "query_vector dimension does not match the pgvector runtime metadata: "
                f"expected {runtime_metadata.vector_dimension}, got {len(normalized_vector)}"
            )

        search_sql = render_pgvector_search_sql(schema_name=self.schema_name)
        query_vector_literal = render_vector_literal(normalized_vector)

        with self._connection_factory(self.dsn, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    search_sql,
                    {
                        "query_vector": query_vector_literal,
                        "top_k": int(top_k),
                        "runtime_id": self.runtime_id,
                    },
                )
                rows = cursor.fetchall()

        matches: list[PgvectorSearchMatch] = []
        for row in rows:
            payload = dict(row)
            raw_score = float(payload.pop("raw_score"))
            payload["section_path"] = list(payload.get("section_path") or [])
            matches.append(
                PgvectorSearchMatch(
                    chunk=ChunkRecord.from_dict(payload),
                    raw_score=raw_score,
                )
            )
        return matches


def render_pgvector_search_sql(*, schema_name: str) -> str:
    validated_schema_name = validate_pgvector_schema_name(schema_name)
    chunks_table = _qualified_table_name(validated_schema_name, DEFAULT_PGVECTOR_CHUNKS_TABLE)
    embeddings_table = _qualified_table_name(
        validated_schema_name,
        DEFAULT_PGVECTOR_EMBEDDINGS_TABLE,
    )
    metadata_table = _qualified_table_name(validated_schema_name, DEFAULT_PGVECTOR_METADATA_TABLE)
    return "\n".join(
        [
            "SELECT",
            "  chunks.snapshot_id,",
            "  chunks.doc_id,",
            "  chunks.chunk_id,",
            "  chunks.section_id,",
            "  chunks.section_index,",
            "  chunks.chunk_index,",
            "  chunks.doc_title,",
            "  chunks.section_path,",
            "  chunks.source_path,",
            "  chunks.source_url,",
            "  chunks.license,",
            "  chunks.attribution,",
            "  chunks.language,",
            "  chunks.start_offset,",
            "  chunks.end_offset,",
            "  chunks.token_count,",
            "  chunks.text,",
            "  1 - (embeddings.embedding <=> %(query_vector)s::vector) AS raw_score",
            f"FROM {embeddings_table} AS embeddings",
            f"JOIN {chunks_table} AS chunks ON chunks.chunk_id = embeddings.chunk_id",
            f"JOIN {metadata_table} AS metadata ON metadata.runtime_id = %(runtime_id)s",
            "ORDER BY embeddings.embedding <=> %(query_vector)s::vector ASC, chunks.chunk_id ASC",
            "LIMIT %(top_k)s",
        ]
    )


def load_pgvector_runtime_metadata(
    *,
    dsn: str,
    schema_name: str = DEFAULT_PGVECTOR_SCHEMA_NAME,
    runtime_id: str = DEFAULT_PGVECTOR_RUNTIME_ID,
    connection_factory: ConnectionFactory | None = None,
) -> PgvectorRuntimeMetadata:
    validated_dsn = _validate_required_string(dsn, field_name="dsn")
    validated_runtime_id = _validate_required_string(runtime_id, field_name="runtime_id")
    validated_schema_name = validate_pgvector_schema_name(schema_name)
    metadata_table = _qualified_table_name(validated_schema_name, DEFAULT_PGVECTOR_METADATA_TABLE)
    resolver = connection_factory or psycopg.connect
    with resolver(validated_dsn, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {metadata_table} WHERE runtime_id = %(runtime_id)s",
                {"runtime_id": validated_runtime_id},
            )
            row = cursor.fetchone()
    if row is None:
        raise ValueError(
            "pgvector runtime metadata is missing. Load the runtime dataset first with the "
            "promote-pgvector-runtime command."
        )
    return PgvectorRuntimeMetadata.from_mapping(row)


def promote_pgvector_runtime(
    *,
    dsn: str,
    chunks_path: Path,
    embedding_metadata_path: Path,
    schema_name: str = DEFAULT_PGVECTOR_SCHEMA_NAME,
    runtime_id: str = DEFAULT_PGVECTOR_RUNTIME_ID,
    connection_factory: ConnectionFactory | None = None,
) -> PgvectorPromotionReport:
    validated_dsn = _validate_required_string(dsn, field_name="dsn")
    validated_schema_name = validate_pgvector_schema_name(schema_name)
    validated_runtime_id = _validate_required_string(runtime_id, field_name="runtime_id")
    resolver = connection_factory or psycopg.connect

    chunks = load_chunk_records(chunks_path)
    embedding_metadata = read_embedding_metadata(embedding_metadata_path)
    vectors_path = _resolve_vectors_path(
        embedding_metadata_path=embedding_metadata_path,
        metadata=embedding_metadata,
    )
    vectors = read_vector_rows(vectors_path, dimension=embedding_metadata.vector_dimension)

    if len(chunks) != embedding_metadata.row_count:
        raise ValueError(
            "Chunk artifact count does not match embedding metadata row count: "
            f"expected {embedding_metadata.row_count}, got {len(chunks)}"
        )
    if len(vectors) != embedding_metadata.row_count:
        raise ValueError(
            "Vector artifact row count does not match embedding metadata row count: "
            f"expected {embedding_metadata.row_count}, got {len(vectors)}"
        )

    runtime_metadata = PgvectorRuntimeMetadata.from_embedding_metadata(
        embedding_metadata,
        runtime_id=validated_runtime_id,
        embedding_metadata_path=embedding_metadata_path,
    )
    chunk_insert_rows = _build_chunk_insert_rows(chunks)
    embedding_insert_rows = _build_embedding_insert_rows(chunks, vectors)

    with resolver(validated_dsn) as connection:
        with connection.cursor() as cursor:
            _reset_pgvector_schema(
                cursor,
                schema_name=validated_schema_name,
                vector_dimension=runtime_metadata.vector_dimension,
            )
            cursor.execute(
                _render_runtime_metadata_insert_sql(validated_schema_name),
                runtime_metadata.to_insert_mapping(),
            )
            cursor.executemany(
                _render_chunk_insert_sql(validated_schema_name),
                chunk_insert_rows,
            )
            cursor.executemany(
                _render_embedding_insert_sql(validated_schema_name),
                embedding_insert_rows,
            )
        connection.commit()

    return PgvectorPromotionReport(
        schema_name=validated_schema_name,
        runtime_id=validated_runtime_id,
        row_count=runtime_metadata.row_count,
        vector_dimension=runtime_metadata.vector_dimension,
        embedding_model_name=runtime_metadata.embedding_model_name,
        source_chunks_path=runtime_metadata.source_chunks_path,
        embedding_metadata_path=runtime_metadata.embedding_metadata_path,
    )


def render_pgvector_promotion_report(report: PgvectorPromotionReport) -> str:
    return "\n".join(
        [
            "pgvector runtime promotion",
            f"schema: {report.schema_name}",
            f"runtime_id: {report.runtime_id}",
            f"rows: {report.row_count}",
            f"vector dimension: {report.vector_dimension}",
            f"embedding model: {report.embedding_model_name}",
            f"source chunks: {report.source_chunks_path}",
            f"embedding metadata: {report.embedding_metadata_path}",
            "status: ok",
        ]
    )


def _resolve_vectors_path(*, embedding_metadata_path: Path, metadata: EmbeddingMetadata) -> Path:
    if metadata.vectors_path:
        resolved = Path(metadata.vectors_path)
        if not resolved.is_absolute():
            resolved = embedding_metadata_path.parent / resolved
        return resolved
    return embedding_metadata_path.parent / "chunk_embeddings.f32"


def _build_chunk_insert_rows(chunks: Iterable[ChunkRecord]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunks:
        rows.append(
            {
                "snapshot_id": chunk.snapshot_id,
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "section_id": chunk.section_id,
                "section_index": chunk.section_index,
                "chunk_index": chunk.chunk_index,
                "doc_title": chunk.doc_title,
                "section_path": Jsonb(list(chunk.section_path)),
                "source_path": chunk.source_path,
                "source_url": chunk.source_url,
                "license": chunk.license,
                "attribution": chunk.attribution,
                "language": chunk.language,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
                "token_count": chunk.token_count,
                "text": chunk.text,
            }
        )
    return rows


def _build_embedding_insert_rows(
    chunks: Sequence[ChunkRecord],
    vectors: Sequence[Sequence[float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "embedding": render_vector_literal(vector),
            }
        )
    return rows


def _reset_pgvector_schema(cursor, *, schema_name: str, vector_dimension: int) -> None:
    validated_schema_name = validate_pgvector_schema_name(schema_name)
    if vector_dimension <= 0:
        raise ValueError("vector_dimension must be > 0")

    qualified_chunks_table = _qualified_table_name(
        validated_schema_name,
        DEFAULT_PGVECTOR_CHUNKS_TABLE,
    )
    qualified_embeddings_table = _qualified_table_name(
        validated_schema_name,
        DEFAULT_PGVECTOR_EMBEDDINGS_TABLE,
    )
    qualified_metadata_table = _qualified_table_name(
        validated_schema_name,
        DEFAULT_PGVECTOR_METADATA_TABLE,
    )

    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{validated_schema_name}"')
    cursor.execute(f"DROP TABLE IF EXISTS {qualified_embeddings_table}")
    cursor.execute(f"DROP TABLE IF EXISTS {qualified_chunks_table}")
    cursor.execute(f"DROP TABLE IF EXISTS {qualified_metadata_table}")

    cursor.execute(
        f"""
        CREATE TABLE {qualified_metadata_table} (
            runtime_id text PRIMARY KEY,
            artifact_version text NOT NULL,
            snapshot_id text NULL,
            embedding_model_name text NOT NULL,
            vector_dimension integer NOT NULL,
            row_count integer NOT NULL,
            source_chunks_path text NOT NULL,
            embedding_metadata_path text NOT NULL,
            vectors_path text NOT NULL,
            distance_metric text NOT NULL
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE {qualified_chunks_table} (
            chunk_id text PRIMARY KEY,
            snapshot_id text NOT NULL,
            doc_id text NOT NULL,
            section_id text NOT NULL,
            section_index integer NOT NULL,
            chunk_index integer NOT NULL,
            doc_title text NOT NULL,
            section_path jsonb NOT NULL,
            source_path text NOT NULL,
            source_url text NOT NULL,
            license text NOT NULL,
            attribution text NOT NULL,
            language text NOT NULL,
            start_offset integer NOT NULL,
            end_offset integer NOT NULL,
            token_count integer NOT NULL,
            text text NOT NULL
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE {qualified_embeddings_table} (
            chunk_id text PRIMARY KEY REFERENCES {qualified_chunks_table} (chunk_id) ON DELETE CASCADE,
            embedding vector({int(vector_dimension)}) NOT NULL
        )
        """
    )


def _render_runtime_metadata_insert_sql(schema_name: str) -> str:
    table_name = _qualified_table_name(schema_name, DEFAULT_PGVECTOR_METADATA_TABLE)
    return f"""
    INSERT INTO {table_name} (
        runtime_id,
        artifact_version,
        snapshot_id,
        embedding_model_name,
        vector_dimension,
        row_count,
        source_chunks_path,
        embedding_metadata_path,
        vectors_path,
        distance_metric
    ) VALUES (
        %(runtime_id)s,
        %(artifact_version)s,
        %(snapshot_id)s,
        %(embedding_model_name)s,
        %(vector_dimension)s,
        %(row_count)s,
        %(source_chunks_path)s,
        %(embedding_metadata_path)s,
        %(vectors_path)s,
        %(distance_metric)s
    )
    """


def _render_chunk_insert_sql(schema_name: str) -> str:
    table_name = _qualified_table_name(schema_name, DEFAULT_PGVECTOR_CHUNKS_TABLE)
    return f"""
    INSERT INTO {table_name} (
        snapshot_id,
        doc_id,
        chunk_id,
        section_id,
        section_index,
        chunk_index,
        doc_title,
        section_path,
        source_path,
        source_url,
        license,
        attribution,
        language,
        start_offset,
        end_offset,
        token_count,
        text
    ) VALUES (
        %(snapshot_id)s,
        %(doc_id)s,
        %(chunk_id)s,
        %(section_id)s,
        %(section_index)s,
        %(chunk_index)s,
        %(doc_title)s,
        %(section_path)s,
        %(source_path)s,
        %(source_url)s,
        %(license)s,
        %(attribution)s,
        %(language)s,
        %(start_offset)s,
        %(end_offset)s,
        %(token_count)s,
        %(text)s
    )
    """


def _render_embedding_insert_sql(schema_name: str) -> str:
    table_name = _qualified_table_name(schema_name, DEFAULT_PGVECTOR_EMBEDDINGS_TABLE)
    return f"""
    INSERT INTO {table_name} (
        chunk_id,
        embedding
    ) VALUES (
        %(chunk_id)s,
        %(embedding)s::vector
    )
    """


def _qualified_table_name(schema_name: str, table_name: str) -> str:
    validated_schema_name = validate_pgvector_schema_name(schema_name)
    validated_table_name = validate_pgvector_schema_name(table_name)
    return f'"{validated_schema_name}"."{validated_table_name}"'


def render_vector_literal(vector: Sequence[float]) -> str:
    normalized = [float(value) for value in vector]
    if not normalized:
        raise ValueError("vector must not be empty")
    return "[" + ",".join(_format_float(value) for value in normalized) + "]"


def _format_float(value: float) -> str:
    formatted = format(float(value), ".10g")
    if formatted == "-0":
        return "0"
    return formatted


def _validate_required_string(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


__all__ = [
    "DEFAULT_PGVECTOR_CHUNKS_TABLE",
    "DEFAULT_PGVECTOR_DISTANCE_METRIC",
    "DEFAULT_PGVECTOR_EMBEDDINGS_TABLE",
    "DEFAULT_PGVECTOR_METADATA_TABLE",
    "DEFAULT_PGVECTOR_RUNTIME_ID",
    "DEFAULT_PGVECTOR_SCHEMA_NAME",
    "PgvectorDenseIndexBackend",
    "PgvectorPromotionReport",
    "PgvectorRuntimeMetadata",
    "PgvectorSearchMatch",
    "load_pgvector_runtime_metadata",
    "promote_pgvector_runtime",
    "render_pgvector_promotion_report",
    "render_pgvector_search_sql",
    "render_vector_literal",
    "validate_pgvector_schema_name",
]
