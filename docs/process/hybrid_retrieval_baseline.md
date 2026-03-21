# Hybrid Retrieval Baseline

This document records the default hybrid retrieval baseline used for Epic 4 comparisons.

## Goal

Run the committed development QA dataset against a dense FAISS index plus the canonical `chunks.jsonl` artifact, then fuse dense and BM25 candidates into one ranked result list with Reciprocal Rank Fusion (RRF).

The baseline writes:

- per-query ranked retrieval results (`.results.jsonl`)
- summary metrics (`.summary.json`)

## Default baseline configuration

- Retriever name: `hybrid-rrf`
- Fusion strategy: Reciprocal Rank Fusion (`rrf`)
- Dense retriever: `dense-faiss`
- Lexical retriever: `bm25`
- Corpus artifact: `data/processed/chunks.jsonl`
- Dense index artifact: `data/processed/indexes/faiss/chunk_index.faiss`
- Dense index metadata: `data/processed/indexes/faiss/chunk_index.metadata.json`
- Default `rrf_k`: `60`
- Default candidate depth: `20`
- Default top-k: `5`
- Dataset: `data/evaluation/dev_qa.k8s-9e1e32b.v1.jsonl`

## Fusion strategy

Hybrid retrieval uses a single deterministic fusion strategy:

- collect ranked candidates from dense FAISS retrieval
- collect ranked candidates from BM25 lexical retrieval
- assign each candidate an RRF contribution of `1 / (rrf_k + rank)` per source retriever
- sum contributions by `chunk_id`
- merge duplicate chunk IDs into one fused entry
- break score ties by ascending `chunk_id`

Duplicate chunk IDs across dense and BM25 are merged deterministically. Metadata from the first observed hit is preserved and enriched with source rank provenance such as:

- `dense-faiss_rank`
- `bm25_rank`

## Output paths

By default, the hybrid baseline writes deterministic artifacts under:

- `data/evaluation/runs/hybrid-rrf-k8s-9e1e32b-v1-top5-default.results.jsonl`
- `data/evaluation/runs/hybrid-rrf-k8s-9e1e32b-v1-top5-default.summary.json`

You can override either path explicitly from the CLI.

## Exact local command

After local chunk, embedding, and FAISS index artifacts exist, run:

```bash
uv run python -m supportdoc_rag_chatbot run-hybrid-baseline \
  --chunks data/processed/chunks.jsonl \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json \
  --top-k 5
```

The command loads the committed Dev QA set, retrieves dense and lexical candidates, fuses them with RRF, and writes deterministic result artifacts.

## Smoke test workflow

This smoke path avoids depending on a committed local `chunks.jsonl` file by using the fixture-based hybrid baseline test.

```bash
uv sync --locked --extra dev-tools --extra faiss --extra bm25
uv run ruff check . --fix
uv run ruff format .
uv run ruff format --check .
uv run pytest -q tests/test_hybrid_baseline.py
uv run pytest -q
```
