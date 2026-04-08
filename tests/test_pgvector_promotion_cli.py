from __future__ import annotations

from pathlib import Path

import pytest

from supportdoc_rag_chatbot.cli import main
from supportdoc_rag_chatbot.retrieval.indexes import PgvectorPromotionReport


def test_promote_pgvector_runtime_cli_prints_success(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    observed: dict[str, object] = {}

    def fake_promote_pgvector_runtime(**kwargs) -> PgvectorPromotionReport:
        observed.update(kwargs)
        return PgvectorPromotionReport(
            schema_name="supportdoc_rag",
            runtime_id="default",
            row_count=1,
            vector_dimension=2,
            embedding_model_name="demo-model",
            source_chunks_path="data/processed/chunks.jsonl",
            embedding_metadata_path="data/processed/embeddings/chunk_embeddings.metadata.json",
        )

    monkeypatch.setattr(
        "supportdoc_rag_chatbot.cli.promote_pgvector_runtime",
        fake_promote_pgvector_runtime,
    )

    exit_code = main(
        [
            "promote-pgvector-runtime",
            "--database-url",
            "postgresql://demo:demo@localhost:5432/supportdoc",
            "--chunks",
            "data/processed/chunks.jsonl",
            "--embedding-metadata",
            "data/processed/embeddings/chunk_embeddings.metadata.json",
            "--schema-name",
            "supportdoc_rag",
            "--runtime-id",
            "default",
        ]
    )

    assert exit_code == 0
    assert observed == {
        "dsn": "postgresql://demo:demo@localhost:5432/supportdoc",
        "chunks_path": Path("data/processed/chunks.jsonl"),
        "embedding_metadata_path": Path("data/processed/embeddings/chunk_embeddings.metadata.json"),
        "schema_name": "supportdoc_rag",
        "runtime_id": "default",
    }

    out = capsys.readouterr().out
    assert "pgvector runtime promotion" in out
    assert "runtime_id: default" in out
    assert "rows: 1" in out
    assert "status: ok" in out
