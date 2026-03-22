# ADR-0003: Embedding Model and Serving Strategy

- **Status:** Accepted
- **Date:** 2026-03-22
- **Deciders:** Rodrigo Arguello Serrano
- **Related:** ADR-0002, ADR-0004, EPIC 3, EPIC 5

## Context

The retrieval stack requires a dense embedding model that is practical for a capstone-scale RAG system, reproducible across runs, and straightforward to serve locally and later in a deployment environment.

The proposal narrows the candidate space to **E5** or **BGE**-class embedding models and allows either local serving or a dedicated embeddings service boundary.

## Decision

Use an **E5/BGE-class dense bi-encoder embedding model** as the semantic retrieval baseline.

The architectural rules are:

- Pin the exact checkpoint in configuration, for example with `EMBEDDING_MODEL_ID`.
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

### 3. Larger embedding models by default

**Pros**
- Potential quality gains
- Broader capability

**Cons**
- Higher memory and latency cost
- More operational complexity
- Unnecessary for the initial scoped corpus

**Why not chosen**
The baseline should optimize for reliability and tractable serving.

## Consequences

### Positive

- Keeps the retrieval stack aligned with semantic search requirements
- Preserves flexibility to benchmark exact E5/BGE checkpoints
- Supports local experimentation and later service isolation
- Improves reproducibility through version pinning

### Negative / Trade-offs

- Requires benchmarking before finalizing a single checkpoint
- Adds an extra component if TEI is introduced later
- Index-time and query-time preprocessing must remain consistent

## Implementation Notes

- Record the final values for `EMBEDDING_MODEL_ID`, revision, vector dimension, and normalization strategy.
- Use the same preprocessing rules for indexing and query embedding.
- Batch embeddings where practical during ingestion.
- Cache document embeddings as durable artifacts when possible.

## Links

- **Proposal:** `Capstone_Project_Proposal_SupportDoc_RAG_Chatbot_with_Citations_V13.md` §5.1, §6.3.2, §10.1, §11.2
- **Code:** `<replace-with-repo-path-to-embedding-config-and-service-code>`
- **Issue:** `<replace-with-sub-issue-number>`

## Follow-up

Replace this placeholder in the committed version with the exact checkpoint pinned in code, for example one specific E5 or BGE model ID. Only one model ID should remain in the final accepted ADR.
