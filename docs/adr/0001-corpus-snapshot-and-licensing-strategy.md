# ADR-0001: Use a pinned Kubernetes documentation snapshot as the initial corpus

- **Status:** Accepted
- **Date:** 2026-03-16
- **Deciders:** Rodrigo Arguello Serrano
- **Tags:** corpus, ingestion, reproducibility, licensing, citations

## Context

The SupportDoc RAG Chatbot requires a single approved documentation corpus for the deployed application. The corpus must be:

- technically realistic for support-style question answering,
- reproducible across ingestion and evaluation runs,
- legally reusable in a citation-driven application, and
- structured enough to support parsing, chunking, retrieval, and provenance tracking.

The project proposal defines the initial production corpus as Kubernetes documentation and requires a fixed snapshot strategy, attribution-aware metadata, and an allowlisted ingestion process. The project kickoff checklist also identifies corpus snapshot and licensing compliance as an early foundation item for the system. 

## Decision

The project will use **Kubernetes documentation** as the initial production corpus.

The corpus will be ingested from a **reproducible pinned snapshot**, using **Git commit hash** as the default snapshot method.

The ingestion pipeline will apply an **allowlist** so that only approved documentation content is included. Initial allowlisted content will focus on technical documentation paths such as:

- `content/en/docs/concepts/**`
- `content/en/docs/tasks/**`
- `content/en/docs/tutorials/**`
- `content/en/docs/reference/**`

The ingestion pipeline will exclude non-target content such as blogs, community pages, GitHub issues/discussions, and other noisy or non-documentation sources.

Each ingested document or chunk must preserve provenance and compliance metadata, including at minimum:

- `source_url`
- `license`
- `attribution`
- `snapshot_id`

The detailed corpus specification will be maintained in:

- `docs/data/corpus.md`

The manifest generation and allowlist enforcement will be implemented in:

- `src/supportdoc_rag_chatbot/ingestion/build_manifest.py`

The generated source manifest artifact will be stored in:

- `data/manifests/source_manifest.jsonl`

## Rationale

Kubernetes documentation was selected because it is a strong fit for a support-oriented RAG system:

1. **Domain fit** 
   It contains installation, configuration, troubleshooting, and reference content that matches the project’s support-assistant use case.

2. **Good structure for retrieval** 
   It is well organized and suitable for parsing into sections and chunks.

3. **Licensing clarity** 
   It supports an attribution-based reuse model compatible with citation rendering in the application.

4. **Reproducibility** 
   A Git commit hash provides a stable and auditable snapshot for ingestion, evaluation, and debugging.

5. **Manageable scope** 
   The allowlist keeps the initial corpus narrow and reduces ingestion noise.

## Consequences

### Positive

- Improves reproducibility across experiments and evaluations.
- Makes citation provenance easier to validate.
- Keeps licensing and attribution handling explicit.
- Reduces retrieval noise by constraining ingestion scope.
- Establishes a clean foundation for later parsing, chunking, and indexing stages.

### Negative / Trade-offs

- Limits the initial domain to Kubernetes documentation only.
- Requires manual maintenance of snapshot metadata.
- Requires allowlist maintenance if corpus scope expands.
- May exclude potentially useful content outside the approved documentation tree.

## Alternatives Considered

### 1. Crawl the live Kubernetes website without pinning a snapshot
Rejected because the corpus would drift over time, making retrieval results and evaluations non-reproducible.

### 2. Use a different technical documentation corpus
Deferred. Other corpora may be added later, but Kubernetes documentation is the initial baseline because it is technically rich, structured, and well aligned with the project goals.

### 3. Ingest all available repository content
Rejected because it would increase noise and risk ingesting irrelevant or low-value content such as blog/community materials.

### 4. Use a dated archive or release tag instead of commit hash
Accepted as fallback options, but Git commit hash is preferred because it is more precise and easier to trace.

## Implementation Notes

- The exact pinned snapshot ID will be recorded in `docs/data/corpus.md`.
- The source manifest will be generated into `data/manifests/source_manifest.jsonl`.
- The allowlist and denylist may evolve, but changes should be reflected in both `corpus.md` and the ingestion code.
- If the corpus strategy changes materially in the future, a new ADR should be created instead of rewriting this one.

## Related Documents

- `PROPOSAL.md`
- `README.md`
- `docs/data/corpus.md`
- `docs/diagrams/ingestion_pipeline.md`
- `src/supportdoc_rag_chatbot/ingestion/build_manifest.py`
- `data/manifests/source_manifest.jsonl`