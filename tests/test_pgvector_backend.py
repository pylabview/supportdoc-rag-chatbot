from __future__ import annotations

import os
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from supportdoc_rag_chatbot.ingestion.jsonl import write_jsonl
from supportdoc_rag_chatbot.ingestion.schemas import ChunkRecord
from supportdoc_rag_chatbot.retrieval.embeddings import EmbeddingMetadata, write_embedding_metadata
from supportdoc_rag_chatbot.retrieval.embeddings.artifacts import write_vector_rows
from supportdoc_rag_chatbot.retrieval.indexes import (
    DEFAULT_PGVECTOR_DISTANCE_METRIC,
    PgvectorDenseIndexBackend,
    PgvectorRuntimeMetadata,
    load_pgvector_runtime_metadata,
    promote_pgvector_runtime,
    render_pgvector_promotion_report,
    render_pgvector_search_sql,
    render_vector_literal,
)


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.rows: list[dict[str, object]] = []

    def execute(self, sql: str, params: dict[str, object] | None = None) -> None:
        self.connection.executed.append(("execute", sql, params))
        self.rows = list(self.connection.execute_handler(sql, params))

    def executemany(self, sql: str, rows) -> None:
        materialized_rows = [dict(row) for row in rows]
        self.connection.executed.append(("executemany", sql, materialized_rows))
        self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, execute_handler) -> None:
        self.execute_handler = execute_handler
        self.executed: list[tuple[str, str, object]] = []
        self.committed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class ConnectionFactory:
    def __init__(self, *connections: FakeConnection) -> None:
        self.connections = list(connections)
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args, **kwargs) -> FakeConnection:
        self.calls.append((args, kwargs))
        return self.connections.pop(0)


def _sample_runtime_metadata_mapping() -> dict[str, object]:
    return {
        "runtime_id": "default",
        "artifact_version": "v1",
        "snapshot_id": "snapshot-001",
        "embedding_model_name": "demo-model",
        "vector_dimension": 2,
        "row_count": 1,
        "source_chunks_path": "data/processed/chunks.jsonl",
        "embedding_metadata_path": "data/processed/embeddings/chunk_embeddings.metadata.json",
        "vectors_path": "data/processed/embeddings/chunk_embeddings.f32",
        "distance_metric": DEFAULT_PGVECTOR_DISTANCE_METRIC,
    }


def _sample_chunk_mapping(*, raw_score: float = 0.9) -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-001",
        "doc_id": "doc-001",
        "chunk_id": "doc-001__chunk-0001",
        "section_id": "section-001",
        "section_index": 0,
        "chunk_index": 0,
        "doc_title": "Pods",
        "section_path": ["Concepts", "Workloads", "Pods"],
        "source_path": "content/en/docs/concepts/workloads/pods/pods.md",
        "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
        "license": "CC BY 4.0",
        "attribution": "Kubernetes Docs",
        "language": "en",
        "start_offset": 0,
        "end_offset": 42,
        "token_count": 8,
        "text": "A Pod is the smallest deployable unit.",
        "raw_score": raw_score,
    }


def _sample_chunk_record() -> ChunkRecord:
    return ChunkRecord.from_dict(_sample_chunk_mapping())


def test_render_pgvector_search_sql_uses_cosine_distance_and_deterministic_ordering() -> None:
    sql = render_pgvector_search_sql(schema_name="supportdoc_rag")

    assert 'FROM "supportdoc_rag"."chunk_embeddings" AS embeddings' in sql
    assert 'JOIN "supportdoc_rag"."chunks" AS chunks' in sql
    assert 'JOIN "supportdoc_rag"."runtime_metadata" AS metadata' in sql
    assert "1 - (embeddings.embedding <=> %(query_vector)s::vector) AS raw_score" in sql
    assert (
        "ORDER BY embeddings.embedding <=> %(query_vector)s::vector ASC, chunks.chunk_id ASC" in sql
    )


def test_render_vector_literal_serializes_query_embeddings() -> None:
    assert render_vector_literal([0.25, -0.5, 0.0]) == "[0.25,-0.5,0]"


def test_load_pgvector_runtime_metadata_reads_runtime_row() -> None:
    connection = FakeConnection(lambda sql, params: [_sample_runtime_metadata_mapping()])
    factory = ConnectionFactory(connection)

    metadata = load_pgvector_runtime_metadata(
        dsn="postgresql://demo:demo@localhost:5432/supportdoc",
        connection_factory=factory,
    )

    assert metadata.runtime_id == "default"
    assert metadata.embedding_model_name == "demo-model"
    assert connection.executed[0][0] == "execute"
    assert "runtime_metadata" in connection.executed[0][1]


def test_pgvector_dense_index_backend_search_maps_rows_into_chunk_records() -> None:
    metadata_connection = FakeConnection(lambda sql, params: [_sample_runtime_metadata_mapping()])
    search_connection = FakeConnection(lambda sql, params: [_sample_chunk_mapping(raw_score=0.75)])
    factory = ConnectionFactory(metadata_connection, search_connection)

    backend = PgvectorDenseIndexBackend(
        dsn="postgresql://demo:demo@localhost:5432/supportdoc",
        connection_factory=factory,
    )

    matches = backend.search([0.1, 0.2], top_k=1)

    assert len(matches) == 1
    assert matches[0].chunk.chunk_id == "doc-001__chunk-0001"
    assert matches[0].raw_score == pytest.approx(0.75)
    assert (
        "1 - (embeddings.embedding <=> %(query_vector)s::vector) AS raw_score"
        in search_connection.executed[0][1]
    )
    assert search_connection.executed[0][2] == {
        "query_vector": "[0.1,0.2]",
        "top_k": 1,
        "runtime_id": "default",
    }


def test_promote_pgvector_runtime_resets_schema_and_loads_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = EmbeddingMetadata(
        artifact_version="v1",
        source_chunks_path="data/processed/chunks.jsonl",
        embedding_model_name="demo-model",
        vector_dimension=2,
        row_count=1,
        snapshot_id="snapshot-001",
        vectors_path="chunk_embeddings.f32",
    )
    connection = FakeConnection(lambda sql, params: [])

    monkeypatch.setattr(
        "supportdoc_rag_chatbot.retrieval.indexes.pgvector_backend.load_chunk_records",
        lambda path: [_sample_chunk_record()],
    )
    monkeypatch.setattr(
        "supportdoc_rag_chatbot.retrieval.indexes.pgvector_backend.read_embedding_metadata",
        lambda path: metadata,
    )
    monkeypatch.setattr(
        "supportdoc_rag_chatbot.retrieval.indexes.pgvector_backend.read_vector_rows",
        lambda path, dimension: [[0.1, 0.2]],
    )

    report = promote_pgvector_runtime(
        dsn="postgresql://demo:demo@localhost:5432/supportdoc",
        chunks_path=Path("data/processed/chunks.jsonl"),
        embedding_metadata_path=Path("data/processed/embeddings/chunk_embeddings.metadata.json"),
        connection_factory=lambda *args, **kwargs: connection,
    )

    assert report.runtime_id == "default"
    assert report.row_count == 1
    assert connection.committed is True
    executed_sql = "\n".join(entry[1] for entry in connection.executed if entry[0] == "execute")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in executed_sql
    assert 'CREATE TABLE "supportdoc_rag"."chunks"' in executed_sql
    assert 'CREATE TABLE "supportdoc_rag"."chunk_embeddings"' in executed_sql
    executemany_rows = [entry for entry in connection.executed if entry[0] == "executemany"]
    assert len(executemany_rows) == 2
    assert executemany_rows[0][2][0]["chunk_id"] == "doc-001__chunk-0001"
    assert isinstance(executemany_rows[0][2][0]["section_path"], Jsonb)
    assert executemany_rows[1][2][0]["embedding"] == "[0.1,0.2]"
    assert "status: ok" in render_pgvector_promotion_report(report)


@pytest.mark.skipif(
    "SUPPORTDOC_TEST_PGVECTOR_DSN" not in os.environ,
    reason="Set SUPPORTDOC_TEST_PGVECTOR_DSN to run the optional pgvector integration test.",
)
def test_pgvector_runtime_round_trip_against_local_postgres(tmp_path: Path) -> None:
    dsn = os.environ["SUPPORTDOC_TEST_PGVECTOR_DSN"]
    schema_name = f"supportdoc_test_{os.getpid()}"
    chunks_path = tmp_path / "chunks.jsonl"
    metadata_path = tmp_path / "chunk_embeddings.metadata.json"
    vectors_path = tmp_path / "chunk_embeddings.f32"
    chunk = _sample_chunk_record()

    write_jsonl(chunks_path, [chunk.to_dict()])
    write_vector_rows(vectors_path, [[0.1, 0.2]])
    write_embedding_metadata(
        metadata_path,
        EmbeddingMetadata(
            artifact_version="v1",
            source_chunks_path=str(chunks_path),
            embedding_model_name="demo-model",
            vector_dimension=2,
            row_count=1,
            snapshot_id="snapshot-001",
            vectors_path=vectors_path.name,
        ),
    )

    try:
        promote_pgvector_runtime(
            dsn=dsn,
            chunks_path=chunks_path,
            embedding_metadata_path=metadata_path,
            schema_name=schema_name,
        )
        backend = PgvectorDenseIndexBackend(
            dsn=dsn,
            schema_name=schema_name,
            connection_factory=None,
        )
        backend._runtime_metadata = PgvectorRuntimeMetadata(
            runtime_id="default",
            artifact_version="v1",
            snapshot_id="snapshot-001",
            embedding_model_name="demo-model",
            vector_dimension=2,
            row_count=1,
            source_chunks_path=str(chunks_path),
            embedding_metadata_path=str(metadata_path),
            vectors_path=str(vectors_path),
        )
        matches = backend.search([0.1, 0.2], top_k=1)
        assert matches[0].chunk.chunk_id == "doc-001__chunk-0001"
    finally:
        import psycopg

        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            connection.commit()
