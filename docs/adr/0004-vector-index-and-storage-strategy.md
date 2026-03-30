# ADR-0004: Vector Index and Storage Strategy

- **Status:** Accepted
- **Date:** 2026-03-22
- **Deciders:** Rodrigo Arguello Serrano
- **Related:** ADR-0002, ADR-0003, EPIC 3, EPIC 5

## Context

The project needs a vector index that is cheap to run, easy to debug, and adequate for a documentation corpus on the order of thousands to low tens of thousands of chunks.

The proposal keeps three options open:

- **FAISS** for the simplest local baseline
- **pgvector** for a Postgres-backed deployment path
- **OpenSearch vector search** for a more managed production path

At the current stage, fast local iteration is more important than managed infrastructure.

## Decision

Use **FAISS as the baseline vector index for local development and experimentation**, while keeping **pgvector** and **OpenSearch vector search** as later upgrade paths.

More specifically:

- Build the first working dense-retrieval baseline on FAISS.
- Keep chunk metadata outside the FAISS index in the metadata store or serialized retrieval artifacts.
- Start with a **simple exact or near-exact index configuration** before introducing more complex ANN structures.
- Treat migration to pgvector or OpenSearch as an explicit later decision, not an implicit implementation drift.

## Alternatives Considered

### 1. pgvector as the first baseline

**Pros**
- Durable storage
- Straightforward SQL-backed operational model
- Easier transition to a service deployment

**Cons**
- More setup than FAISS
- Slower local iteration during early experimentation

**Why not chosen**
The project benefits more from rapid local experimentation at this stage.

### 2. OpenSearch vector search as the first baseline

**Pros**
- Production-style managed service
- Strong fit for later AWS deployment

**Cons**
- Highest operational complexity
- Infrastructure concerns can obscure retrieval debugging

**Why not chosen**
This is a sensible upgrade path, not the best first baseline.

### 3. Custom brute-force vector search

**Pros**
- Transparent behavior
- Minimal abstraction

**Cons**
- Reinvents existing tooling
- Poor scalability
- Unnecessary engineering effort

**Why not chosen**
FAISS already provides a practical, well-understood baseline.

## Consequences

### Positive

- Fast, low-cost retrieval experimentation
- Easier isolation of semantic retrieval quality before deployment work
- Clear migration path to managed storage later

### Negative / Trade-offs

- FAISS is not the final answer for all deployment scenarios
- Metadata joins and persistence live outside the vector index
- Production-scale operational behavior still requires a later storage decision

## Implementation Notes

- Persist the FAISS artifact alongside the chunk metadata snapshot used to build it.
- Version the index with the embedding model ID and corpus snapshot ID.
- Do not switch to a more complex index type until measurements justify it.

## Links

- **Proposal:** `Capstone_Project_Proposal_SupportDoc_RAG_Chatbot_with_Citations_V13.md` §5.1, §6.2, §6.6, §9.2.1, §10.1
- **Code:** `src/supportdoc_rag_chatbot/retrieval/indexes/faiss_backend.py`, `src/supportdoc_rag_chatbot/retrieval/indexes/base.py`, `src/supportdoc_rag_chatbot/cli.py`, `src/supportdoc_rag_chatbot/evaluation/dense_baseline.py`
- **Scope:** `EPIC 3 — Embeddings + vector index (local MVP first)`
