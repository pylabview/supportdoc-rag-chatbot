# Retrieval Comparison Notes

This note summarizes the current dense, BM25, and hybrid retrieval baselines for Epic 4 and records the recommended retrieval default to carry into later epics.

## Scope and evidence base

This comparison is intentionally retrieval-only. It does **not** evaluate answer generation, citation correctness, or refusal behavior.

The current committed repository state targets:

- corpus snapshot: `k8s-9e1e32b`
- committed manifest entries: 2 Kubernetes documents
  - `content/en/docs/concepts/services-networking/service.md`
  - `content/en/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes.md`
- Dev QA dataset: `data/evaluation/dev_qa.k8s-9e1e32b.v1.jsonl`
- Dev QA metadata:
  - dataset name: `dev_qa_retrieval_baselines`
  - dataset version: `v1`
  - query count: `12`
  - registry chunk count: `67`
  - default chunking: `max_tokens=350`, `overlap_tokens=50`

Because the repository does not commit local `data/processed/chunks.jsonl`, embeddings, or FAISS index artifacts, there are no committed corpus-level dense/BM25/hybrid run outputs to compare directly in version control.

For that reason, this note uses **reproducible fixture smoke outputs** from the shared evaluation harness as the reference metrics below and treats the recommendation as a **provisional retrieval default** until local corpus-level artifacts are regenerated.

## Baseline configuration summary

| Baseline | Retriever name | Key config | Default top-k |
| --- | --- | --- | --- |
| Dense | `dense` | embedding model from FAISS metadata (local MVP default: `sentence-transformers/all-MiniLM-L6-v2`); backend `faiss-flat-ip` | `5` |
| BM25 | `bm25` | lowercase regex tokenization `r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*"`; `k1=1.5`; `b=0.75` | `5` |
| Hybrid | `hybrid-rrf` | dense FAISS + BM25 fused with Reciprocal Rank Fusion; `rrf_k=60`; `candidate_depth=20`; deterministic tie-break by ascending `chunk_id` | `5` |

## Reference fixture results

The table below uses the end-to-end fixture smoke outputs that exercise the same evaluation harness and artifact writers used by the real baselines.

These are **reference metrics**, not full corpus-level benchmark numbers.

| Baseline | Fixture run name | Queries | Top-k | hit@k | recall@k | MRR | Mean latency (ms) | Max latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | `dense-k8s-9e1e32b-v1-top2-default` | 2 | 2 | 1.000 | 1.000 | 1.000 | 0.342 | 0.583 |
| BM25 | `bm25-k8s-9e1e32b-v1-top2-default` | 2 | 2 | 1.000 | 1.000 | 1.000 | 0.143 | 0.267 |
| Hybrid | `hybrid-rrf-k8s-9e1e32b-v1-top2-default` | 2 | 2 | 1.000 | 1.000 | 1.000 | 0.695 | 1.265 |

## Qualitative observations

### Dense baseline

Strengths:

- semantic retrieval can recover the correct chunk even when the query wording is not a literal substring of the chunk text
- uses the same FAISS artifact path already established for local dense MVP work

Weaknesses / caveats:

- depends on prebuilt embeddings and a FAISS index, so the local workflow is heavier than BM25
- in the fixture smoke path, the correct chunk is ranked first, but a semantically related non-gold chunk can still appear as the next result when `top_k > 1`

### BM25 baseline

Strengths:

- simplest retrieval stack and easiest artifact model to explain
- deterministic lexical ranking is easy to reproduce and debug
- lowest fixture latency of the three baselines

Weaknesses / caveats:

- strongest on exact lexical overlap, so it is the baseline most likely to miss paraphrases or vocabulary shifts
- depends on a canonical `chunks.jsonl` corpus artifact, which is not committed in the repo today

### Hybrid baseline

Strengths:

- combines semantic and lexical evidence without introducing a reranker
- merges duplicate `chunk_id` values deterministically and preserves source-rank provenance for debugging
- gives the most conservative default for support-document retrieval because it preserves exact-match signals while keeping semantic coverage

Weaknesses / caveats:

- slowest fixture latency because it executes both dense and lexical candidate collection
- when dense and BM25 produce equal fused scores for competing hits, the deterministic tie-break falls back to ascending `chunk_id`; this keeps runs reproducible but means near-tie ordering should be debugged using the stored source-rank metadata rather than fused score alone

## Failure examples / debugging cues

- Dense fixture behavior: the gold chunk is ranked first for both example queries, but the second-ranked result can still be a non-gold semantic neighbor. When investigating dense false positives on real data, inspect the chunk text and embedding model choice before changing the harness.
- BM25 fixture behavior: the baseline returns only the exact lexical hit for each example query. This is a good debugging signal for lexical precision, but it also hints that BM25 may be brittle on paraphrased queries.
- Hybrid tie case: the dedicated hybrid test constructs a dense/BM25 duplicate-hit tie and confirms deterministic fusion. In that scenario, `chunk-noise` and `chunk-service` receive equal RRF mass and the final ordering is resolved by ascending `chunk_id`.

## Recommendation for the next stage

**Recommended default retrieval baseline: `hybrid-rrf`.**

Reasoning:

1. The fixture metrics saturate at `1.0` for all three baselines, so the current tiny smoke dataset does **not** separate the candidates numerically.
2. Given that tie, the decision should favor the retrieval mode with the best risk profile for support-document QA.
3. Hybrid retrieval preserves BM25 exact-match behavior while adding dense semantic coverage, and it already runs through the shared evaluation harness with deterministic duplicate merging and tie-breaking.

This is a **retrieval-only** recommendation. It should be validated again once local corpus-level chunk, embedding, and FAISS artifacts are regenerated and the three baselines are run on the full committed Dev QA set.

Operational recommendation:

- carry `hybrid-rrf` forward as the default retrieval mode for later citation/refusal integration work
- keep `dense` as the semantic-only comparator
- keep `bm25` as the lexical debugging / fallback baseline

## Reproduction workflow

### Fixture-based smoke workflow (works in this repo today)

```bash
uv sync --locked --extra dev-tools --extra faiss --extra bm25
uv run ruff check . --fix
uv run ruff format .
uv run ruff format --check .
uv run pre-commit run --all-files
PYTHONPATH=src uv run pytest -q tests/test_dense_retrieval_baseline.py tests/test_bm25_baseline.py tests/test_hybrid_baseline.py
PYTHONPATH=src uv run pytest -q
```

### Real corpus-level comparison workflow (requires local processed artifacts)

```bash
uv run python -m supportdoc_rag_chatbot run-dense-baseline \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json \
  --top-k 5 \
  --results-output data/evaluation/runs/dense-k8s-9e1e32b-v1-top5-default.results.jsonl \
  --summary-output data/evaluation/runs/dense-k8s-9e1e32b-v1-top5-default.summary.json

uv run python -m supportdoc_rag_chatbot run-bm25-baseline \
  --chunks data/processed/chunks.jsonl \
  --top-k 5 \
  --results-output data/evaluation/runs/bm25-k8s-9e1e32b-v1-top5-default.results.jsonl \
  --summary-output data/evaluation/runs/bm25-k8s-9e1e32b-v1-top5-default.summary.json

uv run python -m supportdoc_rag_chatbot run-hybrid-baseline \
  --chunks data/processed/chunks.jsonl \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json \
  --top-k 5 \
  --results-output data/evaluation/runs/hybrid-rrf-k8s-9e1e32b-v1-top5-default.results.jsonl \
  --summary-output data/evaluation/runs/hybrid-rrf-k8s-9e1e32b-v1-top5-default.summary.json
```

Once those local artifacts exist, update this note with corpus-level summary metrics and qualitative failure examples taken from the committed Dev QA set.
