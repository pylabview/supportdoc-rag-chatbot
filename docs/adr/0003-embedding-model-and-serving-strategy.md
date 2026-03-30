# ADR-0003: Embedding Model and Serving Strategy

- **Status:** Accepted
- **Date:** 2026-03-22
- **Deciders:** Rodrigo Arguello Serrano
- **Related:** ADR-0002, ADR-0004, EPIC 3, EPIC 5

## Context

The retrieval stack requires a dense embedding model that is practical for a capstone-scale RAG system, reproducible across runs, and straightforward to serve locally and later in a deployment environment.

The original proposal narrowed the candidate space to **E5** or **BGE**-class embedding models. The committed repo, however, now pins a lighter local default in code so the API smoke paths and retrieval baselines can run on an ordinary developer machine without a separate embeddings service.

## Decision

Use `sentence-transformers/all-MiniLM-L6-v2` as the **default local dense embedding model** for the current MVP, while keeping the embedding entry points configurable so another checkpoint can be benchmarked and promoted later.

The architectural rules are:

- Pin the exact checkpoint in code and CLI defaults.
- Start with **local/in-process serving** for development simplicity.
- Preserve the option to move embeddings behind a dedicated service boundary, such as **TEI**, when throughput or deployment isolation matters.
- Record the exact model identifier and revision in evaluation artifacts for reproducibility.

## Alternatives Considered

### 1. Proprietary hosted embedding APIs

**Pros**
- Simple setup
- Managed scaling

**Cons**
- Extra dependency
- Cost and rate-limit exposure
- Harder reproducibility
- Less control over local evaluation

**Why not chosen**
The project is explicitly oriented around an open-source, reproducible stack.

### 2. Sparse-only retrieval

**Pros**
- Simpler system
- No embedding service needed

**Cons**
- Misses semantically relevant passages with different phrasing
- Weakens the core semantic-search value proposition

**Why not chosen**
Semantic retrieval is a primary requirement for the support-doc use case.

### 3. Heavier E5 or BGE checkpoints as the immediate default

**Pros**
- Potential quality gains
- Broader capability

**Cons**
- Higher memory and latency cost
- More operational complexity
- Unnecessary for the initial scoped corpus

**Why not chosen**
The baseline should optimize for reliability and tractable serving first. Heavier checkpoints can still be benchmarked later without changing the public retrieval interfaces.

## Consequences

### Positive

- Keeps the retrieval stack aligned with semantic search requirements
- Preserves flexibility to benchmark stronger E5/BGE checkpoints later
- Supports local experimentation and later service isolation
- Improves reproducibility through version pinning

### Negative / Trade-offs

- The lightweight default is a pragmatic runtime choice, not a claim that it is the best final semantic model for every deployment
- Adds an extra component if TEI is introduced later
- Index-time and query-time preprocessing must remain consistent

## Implementation Notes

- Keep `src/supportdoc_rag_chatbot/retrieval/embeddings/models.py` as the source of truth for the default local checkpoint.
- Record the exact model identifier, vector dimension, and normalization strategy in generated embedding metadata.
- Use the same preprocessing rules for indexing and query embedding.
- Batch embeddings where practical during ingestion.
- Cache document embeddings as durable artifacts when possible.

## Links

- **Proposal:** `Capstone_Project_Proposal_SupportDoc_RAG_Chatbot_with_Citations_V13.md` §5.1, §6.3.2, §10.1, §11.2
- **Code:** `src/supportdoc_rag_chatbot/retrieval/embeddings/models.py`, `src/supportdoc_rag_chatbot/retrieval/embeddings/job.py`, `src/supportdoc_rag_chatbot/retrieval/embeddings/artifacts.py`, `src/supportdoc_rag_chatbot/cli.py`
- **Scope:** `EPIC 3 — Embeddings + vector index (local MVP first)`

## Follow-up

Future benchmark work can still supersede this ADR with a different default checkpoint, but the current committed source of truth is `sentence-transformers/all-MiniLM-L6-v2`.
