# Dense Retrieval Baseline

This document records the default dense retrieval baseline used for Epic 4 comparisons.

## Goal

Run the committed development QA dataset against an already-built local FAISS index without rebuilding chunks, embeddings, or index artifacts.

The baseline writes:

- per-query ranked retrieval results (`.results.jsonl`)
- summary metrics (`.summary.json`)

## Default baseline configuration

- Retriever name: `dense`
- Embedding model: recorded in the FAISS index metadata, defaulting to `sentence-transformers/all-MiniLM-L6-v2` for local MVP work
- Index backend: `faiss-flat-ip`
- Default top-k: `5`
- Dataset: `data/evaluation/dev_qa.k8s-9e1e32b.v1.jsonl`

## Output paths

By default, the dense baseline writes deterministic artifacts under:

- `data/evaluation/runs/dense-k8s-9e1e32b-v1-top5-default.results.jsonl`
- `data/evaluation/runs/dense-k8s-9e1e32b-v1-top5-default.summary.json`

You can override either path explicitly from the CLI.

## Exact local command

After local embedding and FAISS index artifacts exist, run:

```bash
uv run python -m supportdoc_rag_chatbot run-dense-baseline \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json \
  --top-k 5
```

The command loads the committed Dev QA set, embeds each question with the embedding model recorded in the FAISS metadata, runs dense retrieval through the shared evaluation harness, and writes deterministic result artifacts.

## Smoke test workflow

```bash
uv sync --locked --extra dev-tools --extra faiss
uv run pytest -q tests/test_dense_retrieval_baseline.py
uv run pre-commit run --all-files
uv run pytest -q
```
