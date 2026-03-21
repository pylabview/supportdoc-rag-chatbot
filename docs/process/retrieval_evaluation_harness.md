# Retrieval Evaluation Harness

This document describes the retrieval-only evaluation harness added for Epic 4 baseline work.

The harness runs a retriever against the committed Dev QA set and writes deterministic, machine-readable artifacts for:

- per-query ranked retrieval outputs
- summary retrieval metrics

It is intentionally retrieval-only. It does **not** evaluate answer generation, citation validation, or refusal behavior.

---

## 1. Goals

The harness exists so dense, BM25, and hybrid retrieval can be compared under the same:

- dataset
- top-k setting
- output schema
- metrics

Without this layer, later comparison notes would be ad hoc and hard to reproduce.

---

## 2. Default inputs

By default, the CLI uses the committed Dev QA set from Issue #37:

- `data/evaluation/dev_qa.k8s-9e1e32b.v1.jsonl`
- `data/evaluation/dev_qa.k8s-9e1e32b.v1.metadata.json`
- `data/evaluation/dev_qa.k8s-9e1e32b.v1.registry.json`

The harness validates the dataset against the metadata and evidence registry before running any retriever.

---

## 3. Retriever interface

Retrievers plug into the harness through a small common interface:

- `name`
- `retriever_type`
- `config`
- `retrieve(entry, top_k)`

Current retriever implementations live in `src/supportdoc_rag_chatbot/evaluation/retrievers.py`:

- `StaticEvaluationRetriever`
- `DenseFaissEvaluationRetriever`
- `BM25ChunkEvaluationRetriever`
- `HybridRRFEvaluationRetriever`

### Notes

- The static retriever is mainly for smoke tests and fixture-driven unit tests.
- The dense retriever wraps the existing FAISS backend and local query embedding flow.
- The BM25 retriever scores `chunks.jsonl` directly and does not require FAISS artifacts.
- The hybrid retriever fuses dense + lexical candidates with Reciprocal Rank Fusion (RRF).

---

## 4. Artifact schema

### 4.1 Per-query results artifact

File format:

- JSONL
- one row per query

Each row includes at least:

- `run_id`
- `dataset_name`
- `dataset_version`
- `snapshot_id`
- `retriever_name`
- `retriever_type`
- `retriever_config`
- `query_id`
- `question`
- `top_k`
- `latency_ms`
- `hit`
- `reciprocal_rank`
- `recall`
- `hits`

Each `hits` item includes at least:

- `chunk_id`
- `rank`
- `score`
- optional `doc_id`
- optional `section_id`
- optional `metadata`

### 4.2 Summary artifact

File format:

- JSON

The summary includes at least:

- `run_id`
- `dataset_name`
- `dataset_version`
- `snapshot_id`
- `retriever_name`
- `retriever_type`
- `retriever_config`
- `top_k`
- `total_query_count`
- `answerable_query_count`
- `unanswerable_query_count`
- `relevant_query_count`
- `hit_at_k`
- `recall_at_k`
- `mrr`
- `average_latency_ms`
- `p50_latency_ms`
- `p95_latency_ms`
- `max_latency_ms`

---

## 5. Metric definitions

Metrics are computed over queries that have at least one expected relevant identifier.

### hit@k

A query counts as a hit if at least one expected relevant identifier appears in the retrieved top-k hits.

### recall@k

Macro-average recall across relevant queries.

- If a query has expected chunk IDs, recall is measured against those chunk IDs.
- If a query has no expected chunk IDs but does have expected section IDs, recall is measured against section IDs.

### MRR

Mean Reciprocal Rank of the first relevant hit across relevant queries.

### latency

Per-query latency is measured around the retriever call and aggregated into average, p50, p95, and max values.

---

## 6. Deterministic output layout

Default run outputs are written under:

- `data/evaluation/runs/`

The default run ID format is:

```text
<snapshot_id>-<dataset_version>-<retriever_type>-<retriever_name>-top<k>
```

Example:

```text
k8s-9e1e32b-v1-dense-dense-faiss-top5
```

Default artifact paths derived from that ID are:

- `data/evaluation/runs/<run_id>.results.jsonl`
- `data/evaluation/runs/<run_id>.summary.json`

These outputs are intentionally ignored by `.gitignore` for local smoke-test use.

---

## 7. Local smoke-test workflow

### 7.1 Zero-dependency harness smoke test

This path verifies the evaluation harness itself without requiring local embeddings, FAISS, or local `chunks.jsonl` artifacts.

```bash
uv sync --locked --extra dev-tools

uv run python -m supportdoc_rag_chatbot evaluate-retrieval \
  --retriever-kind static \
  --fixture-name oracle \
  --top-k 5
```

What this does:

- loads the committed Dev QA dataset
- validates dataset + metadata + evidence registry
- runs an oracle-style static retriever over the dataset
- writes per-query + summary artifacts under `data/evaluation/runs/`

### 7.2 BM25 evaluation over local chunks

If you already have a local `chunks.jsonl` artifact, run:

```bash
uv run python -m supportdoc_rag_chatbot evaluate-retrieval \
  --retriever-kind bm25 \
  --chunks data/processed/chunks.jsonl \
  --top-k 5
```

### 7.3 Dense evaluation over the local FAISS backend

If you want to run the real dense retriever, install the dense extras first:

```bash
uv sync --locked --extra dev-tools --extra embeddings-local --extra faiss
```

Then run:

```bash
uv run python -m supportdoc_rag_chatbot evaluate-retrieval \
  --retriever-kind dense \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json \
  --top-k 5
```

### 7.4 Hybrid dense + lexical evaluation

```bash
uv run python -m supportdoc_rag_chatbot evaluate-retrieval \
  --retriever-kind hybrid \
  --chunks data/processed/chunks.jsonl \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json \
  --top-k 5
```

---

## 8. Testing strategy

The harness is covered by fixture-based unit tests that validate:

- metric computation
- deterministic run IDs and output paths
- artifact writing + loading
- hybrid fusion behavior
- CLI artifact generation with the static fixture retriever

The recommended targeted test command is:

```bash
uv run pytest -q tests/test_retrieval_evaluation_harness.py
```

---

## 9. Scope boundaries

### In scope

- retrieval-only evaluation
- per-query artifacts
- summary metrics
- deterministic output layout
- dense / BM25 / hybrid retriever interface

### Out of scope

- answer generation scoring
- citation precision scoring
- refusal correctness scoring
- reranker experiments
- benchmark datasets beyond the committed Dev QA set
