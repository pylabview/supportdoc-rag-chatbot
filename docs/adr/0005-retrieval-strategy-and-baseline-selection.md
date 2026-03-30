# ADR-0005: Retrieval Strategy and Baseline Selection

- **Status:** Accepted
- **Date:** 2026-03-22
- **Deciders:** Rodrigo Arguello Serrano
- **Related:** ADR-0002, ADR-0003, ADR-0004, EPIC 4, EPIC 5

## Context

The project’s core product claim depends on retrieving the correct evidence before generation. The proposal treats retrieval as an experimentally tuned subsystem and explicitly identifies these candidate configurations:

- **BM25-only**
- **Dense-only**
- **Hybrid retrieval**
- **Optional reranker**

The proposal also defines the winner-selection rule: choose the configuration that maximizes retrieval quality metrics such as recall@k and context precision while keeping latency acceptable.

## Decision

Use **hybrid retrieval as the default target strategy**, while preserving **BM25-only** and **dense-only** as required benchmark baselines.

### Default retrieval shape

- Run a lexical retriever and a dense retriever in parallel.
- Merge candidate sets using **Reciprocal Rank Fusion (RRF)**.
- Use **top-k = 5** as the default evaluation baseline in the committed retrieval comparison artifacts.
- Defer reranking until the baseline retrieval comparison is complete.

### Winner-selection rule

The default configuration must be justified using at least:

- **Recall@k**
- **Context precision / relevance**
- **Retrieval latency**
- **End-to-end latency or TTFT impact**

If later measurements show that a simpler strategy clearly outperforms hybrid retrieval for this corpus and latency budget, this ADR should be superseded with the measured result.

This ADR governs the **retrieval baseline recommendation**. The current checked-in API smoke and evidence-review paths still validate the dense FAISS-backed artifact workflow, not an end-to-end hybrid query path.

## Alternatives Considered

### 1. BM25-only retrieval

**Pros**
- Simple
- Strong exact-match baseline
- Easy to debug

**Cons**
- Misses semantically similar phrasing
- Weaker for natural-language support questions

**Why not chosen as default**
It is an important benchmark, but not the best target architecture.

### 2. Dense-only retrieval

**Pros**
- Strong semantic matching
- Good for paraphrased queries

**Cons**
- Can miss exact identifiers, commands, and product-specific strings
- Harder to inspect when rankings fail

**Why not chosen as default**
Lexical evidence still matters in documentation-heavy workflows.

### 3. Immediate hybrid + reranker

**Pros**
- Often best precision
- Good final-ranking quality

**Cons**
- Higher latency
- More infrastructure complexity
- Harder to reason about baseline quality

**Why not chosen initially**
The baseline hybrid system should be stabilized before adding another ranking stage.

## Consequences

### Positive

- Balances semantic coverage and exact-match behavior
- Keeps baseline comparisons honest and repeatable
- Leaves a clean path to later reranking if the gain is worth the latency cost

### Negative / Trade-offs

- More moving parts than a single retriever
- Requires candidate-fusion logic and tuning
- Debugging can be harder when lexical and dense signals disagree

## Implementation Notes

- Keep BM25-only and dense-only runnable as first-class baselines.
- Log component-level retrieval scores where practical.
- Record `k`, fusion method, and retriever configuration in evaluation artifacts.
- Keep this ADR linked to the committed retrieval comparison note and hybrid-baseline process doc.

## Links

- **Proposal:** `Capstone_Project_Proposal_SupportDoc_RAG_Chatbot_with_Citations_V13.md` §5.2, §6.2, §7.3.1, §7.4, §7.5, §10.1, §11.3
- **Code:** `src/supportdoc_rag_chatbot/evaluation/retrievers.py`, `src/supportdoc_rag_chatbot/evaluation/dense_baseline.py`, `src/supportdoc_rag_chatbot/evaluation/bm25_baseline.py`, `src/supportdoc_rag_chatbot/evaluation/hybrid_baseline.py`
- **Scope:** `EPIC 4 — Retrieval baselines (dense / BM25 / hybrid)`
- **Evaluation artifact:** `docs/process/retrieval_comparison_notes.md`, `docs/process/hybrid_retrieval_baseline.md`
