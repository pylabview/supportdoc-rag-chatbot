# Retrieval Sufficiency Gating

This document records the deterministic backend policy that decides whether retrieved evidence is strong enough for full generation, thin/capped generation, or an explicit refusal.

## Goal

Given ranked retrieval results for one request, compute stable score aggregates and emit a machine-readable action before trusting model output.

The policy is intentionally deterministic so later FastAPI orchestration can reuse it directly for logging, refusal handling, and prompt-mode selection.

## Module entry points

- `src/supportdoc_rag_chatbot/app/services/policy_types.py`
- `src/supportdoc_rag_chatbot/app/services/refusal_policy.py`
- `src/supportdoc_rag_chatbot/resources/default_config.yaml`

## Explicit score-normalization assumption

The initial thresholds assume **unit-interval normalized scores** (`0.0` to `1.0`).

This matters because dense cosine similarities, BM25 scores, and hybrid RRF scores are not inherently comparable. The request payload and checked-in config both carry a `score_normalization` field, and the policy raises a clear error when the request normalization mode does not match the threshold config.

That makes the calibration assumption explicit instead of silently applying one threshold set to incompatible score scales.

## Thresholds

The checked-in default policy currently uses:

- `k = 8`
- `T_top1 = 0.75`
- `T_mean3 = 0.60`
- `T_support = 0.55`
- `N_support = 2`
- `L_thin_max = 3`
- `T_nohit = 0.20`

These defaults are provisional and meant to be re-calibrated later on a development set.

## Aggregates

For the top `k` ranked hits only, the policy computes:

- `top1_score`
- `mean_top3_score` over up to the first three available hits
- `support_count` = number of chunks with `score >= T_support`

When fewer than three hits are available, `mean_top3_score` uses the available prefix only. Sparse retrieval can still pass the refusal checks, but it is forced into the thin/capped branch instead of a full answer.

## Decision branches

### Refuse as `no_relevant_docs`

Refuse when:

- no hits are available, or
- `T_nohit` is configured and `top1_score < T_nohit`

### Refuse as `insufficient_evidence`

Refuse when any of these conditions fail:

- `top1_score >= T_top1`
- `mean_top3_score >= T_mean3`
- `support_count >= N_support`

### Allow thin / capped answer

Allow a thin answer when the refusal thresholds pass but evidence is still sparse or barely sufficient:

- `support_count == N_support`, or
- fewer than three hits are available

The decision exposes `max_answer_sentences = L_thin_max` for later orchestration.

### Allow full answer

Allow a full answer only when the refusal thresholds pass and the thin-answer conditions do not apply.

## Diagnostics

Every decision includes machine-readable diagnostics suitable for logs:

- normalization mode
- thresholds used
- aggregated score summary
- `failing_conditions`
- `thin_reasons`

Current diagnostic condition codes:

- `no_hit_floor`
- `low_top1`
- `low_mean3`
- `insufficient_support`
- `sparse_context`
- `support_floor_only`

## Exact local smoke command

```bash
uv run python -m supportdoc_rag_chatbot smoke-retrieval-sufficiency \
  --config src/supportdoc_rag_chatbot/resources/default_config.yaml
```

The smoke command exercises deterministic full-answer, thin-answer, no-hit refusal, and insufficient-evidence refusal branches against the checked-in thresholds.
