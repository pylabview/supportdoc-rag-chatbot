# ADR-0002: Ingestion Pipeline and Chunking Strategy

- **Status:** Accepted
- **Date:** 2026-03-22
- **Deciders:** Rodrigo Arguello Serrano
- **Related:** ADR-0001, EPIC 2, EPIC 5

## Context

The project ingests an allowlisted documentation corpus from a fixed snapshot and transforms it into retrievable chunks for downstream RAG. The ingestion pipeline must support reproducibility, retrieval quality, provenance, and later citation validation.

A naive sliding-window approach is easy to implement but weak for traceability and often fragments meaning. Page-level chunks preserve context but add too much irrelevant text to retrieval and prompting. The project needs a deterministic, section-aware approach that preserves structure while remaining easy to debug.

## Decision

Use a **deterministic, section-aware ingestion pipeline**:

- Parse documentation into a structured representation before chunking.
- Prefer **section/subsection boundaries** as the primary chunk boundary.
- Apply a **token cap** only when sections are too large.
- Use moderate overlap only when a section split is required.
- Preserve stable chunk metadata for provenance and citation validation.

### Baseline chunking rules

- **Primary boundary:** section/subsection structure from Markdown or HTML parsing
- **Target chunk size:** about **350–800 tokens**
- **Overlap:** about **50–120 tokens** when splitting large sections
- Keep headings and nearby context attached to each chunk whenever practical

### Required metadata

Each chunk should preserve at least:

```json
{
  "doc_id": "string",
  "doc_title": "string",
  "section_path": "string",
  "chunk_id": "string",
  "start_offset": 0,
  "end_offset": 0,
  "source_url": "string",
  "license": "string",
  "snapshot_id": "string"
}
```

## Alternatives Considered

### 1. Fixed-size sliding windows

**Pros**
- Simple implementation
- Uniform chunk sizes

**Cons**
- Breaks semantic structure
- Produces awkward evidence spans
- Makes citation mapping less intuitive

**Why not chosen**
The project needs chunks that are easy to reason about and validate later.

### 2. Page-level or document-level chunks

**Pros**
- Minimal preprocessing
- Strong coherence

**Cons**
- Too much irrelevant context per retrieval result
- Higher prompt cost
- Lower ranking precision on focused troubleshooting questions

**Why not chosen**
The system needs targeted evidence retrieval, not broad page retrieval.

### 3. Sentence-level chunks

**Pros**
- Fine-grained evidence mapping
- Useful for narrow fact lookups

**Cons**
- Fragments explanations and procedures
- Hurts recall for multi-step answers
- Requires more downstream reassembly

**Why not chosen**
The baseline should preserve enough standalone meaning for retrieval and generation.

## Consequences

### Positive

- Better retrieval quality by aligning chunks to author-written structure
- Stable provenance for later citation enforcement
- Deterministic, testable ingestion behavior
- Lower prompt noise than page-level chunks

### Negative / Trade-offs

- Parsing is more complex than plain text splitting
- Token-aware splitting adds a tokenizer dependency
- Chunk size and overlap remain tuning parameters

## Implementation Notes

- Normalize formatting before token counting so offsets remain stable.
- Generate chunk IDs deterministically from document identity and section/split position.
- Keep parsing, normalization, chunking, and metadata generation as separate stages.
- Record ingestion counts and total token counts for reproducibility reporting.

## Links

- **Proposal:** `Capstone_Project_Proposal_SupportDoc_RAG_Chatbot_with_Citations_V13.md` §4.4, §5.2, §6.3, §10.1, §11.1
- **Code:** `src/supportdoc_rag_chatbot/ingestion/build_manifest.py`, `src/supportdoc_rag_chatbot/ingestion/parse_docs.py`, `src/supportdoc_rag_chatbot/ingestion/chunk_docs.py`, `src/supportdoc_rag_chatbot/ingestion/chunker.py`, `src/supportdoc_rag_chatbot/ingestion/validator.py`
- **Scope:** `EPIC 2 — Ingestion pipeline (parse → chunk → metadata)`
