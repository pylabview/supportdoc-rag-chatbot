# BM25 Retrieval Baseline

This document records the default BM25 retrieval baseline used for Epic 4 comparisons.

## Goal

Run the committed development QA dataset against the canonical `chunks.jsonl` artifact without rebuilding chunks, embeddings, or index artifacts.

The baseline writes:

- per-query ranked retrieval results (`.results.jsonl`)
- summary metrics (`.summary.json`)

## Default baseline configuration

- Retriever name: `bm25`
- Corpus artifact: `data/processed/chunks.jsonl`
- Tokenization: lowercase regex tokenization using `r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*"`
- BM25 parameters:
  - `k1 = 1.5`
  - `b = 0.75`
- Default top-k: `5`
- Dataset: `data/evaluation/dev_qa.k8s-9e1e32b.v1.jsonl`

## Tokenization / normalization strategy

BM25 scoring uses a deterministic lexical tokenizer:

- extract tokens with the regex `r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*"`
- lowercase every token
- ignore punctuation outside the token pattern
- preserve separators such as `.`, `_`, `:`, `/`, and `-` when they appear inside a token

Examples:

- `Kubernetes Service` -> `kubernetes`, `service`
- `slow-starting` -> `slow-starting`
- `v1/pods` -> `v1/pods`

## Output paths

By default, the BM25 baseline writes deterministic artifacts under:

- `data/evaluation/runs/bm25-k8s-9e1e32b-v1-top5-default.results.jsonl`
- `data/evaluation/runs/bm25-k8s-9e1e32b-v1-top5-default.summary.json`

You can override either path explicitly from the CLI.

## Exact local command

After `data/processed/chunks.jsonl` exists, run:

```bash
uv run python -m supportdoc_rag_chatbot run-bm25-baseline \
  --chunks data/processed/chunks.jsonl \
  --top-k 5
```

The command loads the committed Dev QA set, tokenizes the query and chunk corpus deterministically, runs BM25 retrieval through the shared evaluation harness, and writes deterministic result artifacts.

## Smoke test workflow

This smoke path avoids depending on a committed local `chunks.jsonl` file by using the fixture-based test for the BM25 baseline.

```bash
uv sync --locked --extra dev-tools --extra bm25
uv run ruff check . --fix
uv run ruff format --check .
uv run pytest -q tests/test_bm25_baseline.py
uv run pytest -q
```
