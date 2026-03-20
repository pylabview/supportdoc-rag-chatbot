## 1. Project Overview

SupportDoc RAG Chatbot is a document-grounded support assistant that answers user questions using an approved documentation corpus and provides verifiable citations to the exact supporting source passages. The project is designed to reduce hallucinations by combining retrieval-augmented generation (RAG), citation validation, and explicit refusal behavior when evidence is missing or insufficient.

The long-term goal is to deliver a production-style web application with a clear separation between ingestion, retrieval, generation, validation, and deployment concerns. At a high level, the system ingests an allowlisted documentation snapshot, converts it into structured chunks with provenance metadata, retrieves relevant evidence for a user query, generates an answer using an open-source LLM, and returns citations for each supported claim. If the retrieved evidence is weak, incomplete, or fails validation, the system refuses rather than guessing.

The initial corpus is a pinned snapshot of Kubernetes documentation so the project can iterate on retrieval, answer grounding, and citation validation against a reproducible support-doc dataset.

---

## 2. Current Status

This README is maintained as a live project document and evolves with each completed task issue.

### Current Phase
Local dense retrieval baseline.

### Completed
- Repository scaffolding for application, ingestion, retrieval, evaluation, and documentation.
- Corpus governance documentation in `docs/data/corpus.md`.
- Ingestion pipeline artifacts for manifest generation, parsing, section extraction, chunking, and validation.
- Stable `chunks.jsonl` artifact with chunk-level provenance metadata.
- Local embedding job that converts `data/processed/chunks.jsonl` into deterministic dense-vector artifacts for downstream index construction.
- Local FAISS backend that builds, persists, reloads, and searches a dense index over saved embedding artifacts.
- Developer-facing retrieval smoke CLI for local dense search over a saved FAISS index.

### In Progress
- Citation contract and refusal behavior integration.

### Next Up
- Add dense retrieval smoke tests and baseline retrieval evaluation.
- Connect retrieval outputs to generation and citation validation.
- Expand deployment and observability documentation as the backend/API layer matures.
- Add alternative retrieval backends behind the same interface as the project moves beyond the local MVP.

---

## 3. Architecture Overview

The project follows a three-layer architecture:

### Model Layer
This layer contains the ML components used for embeddings and answer generation. For local retrieval development, the project currently defaults to a lightweight sentence-transformers embedding model suitable for laptop workflows, while keeping the embedding model configurable so E5, BGE, or hosted embedding backends can be swapped in later.

### Application Layer
This is the main orchestration layer implemented in this repository. It is responsible for:
- corpus ingestion,
- manifest generation,
- parsing and chunking,
- embedding artifact generation,
- retrieval orchestration,
- answer generation,
- citation validation, and
- refusal enforcement.

### Infrastructure Layer
The intended deployment target is an AWS-backed web application with a frontend, backend API, vector search layer, and model-serving component. The proposal currently targets a React-based UI, a FastAPI backend, object storage for artifacts, and a vector store such as FAISS, pgvector, or OpenSearch depending on the stage of the project.

### High-Level System Flow

```mermaid
flowchart TB
    U[User Question] --> API[Application / API Layer]
    API --> RET[Retrieval Layer]
    RET --> VDB[(Vector Index / Search)]
    VDB --> API
    API --> LLM[Generation Model]
    LLM --> API
    API --> VAL[Citation Validation + Refusal Policy]
    VAL --> R[Response with Citations or Refusal]

    subgraph Ingestion
        SRC[Corpus Snapshot]
        MAN[Source Manifest]
        PARSE[Parse Docs]
        CHUNK[Chunk + Metadata]
        EMB[Embeddings]
        IDX[Index Build]
        SRC --> MAN --> PARSE --> CHUNK --> EMB --> IDX
    end
```

---

## 4. Embedding Artifacts (Local MVP)

The local embedding step is intentionally backend-agnostic. It reads the canonical chunk artifact and writes:

- a row-major float32 vector artifact,
- a small JSON metadata artifact, and
- no index-specific files yet.

Default output paths:

- `data/processed/embeddings/chunk_embeddings.f32`
- `data/processed/embeddings/chunk_embeddings.metadata.json`

The metadata file records at least:

- source chunks path,
- embedding model name,
- vector dimension,
- row count,
- snapshot ID when all chunk rows share the same snapshot, and
- vector artifact path.

This keeps the embedding job reusable by FAISS, pgvector, or any later retrieval backend.

---


## 4A. Local FAISS Index Artifacts (MVP)

The first dense retrieval backend uses FAISS with a flat inner-product index. For cosine-similarity-compatible retrieval, the backend L2-normalizes database vectors before adding them to `IndexFlatIP`, then normalizes query vectors before search.

Default output paths:

- `data/processed/indexes/faiss/chunk_index.faiss`
- `data/processed/indexes/faiss/chunk_index.metadata.json`
- `data/processed/indexes/faiss/chunk_index.row_mapping.json`

The metadata sidecar records at least:

- backend name,
- metric,
- embedding model name,
- vector dimension,
- row count,
- source chunks path,
- embedding metadata path,
- vector artifact path, and
- snapshot ID when available.

The row-mapping artifact stores the chunk IDs in row order so the FAISS index can stay focused on vector search while chunk provenance remains in the original `chunks.jsonl` artifact.

---

## 5. Repository Structure

```text
src/supportdoc_rag_chatbot/
  ingestion/              # Manifest, parse, chunk, validation pipeline
  retrieval/
    embeddings/           # Local embedding job + artifact I/O
    indexes/              # Dense index interfaces + local FAISS backend
    smoke.py              # Developer-facing dense retrieval smoke helpers
  app/                    # Backend orchestration entrypoints (to grow over time)
  resources/              # Default config and packaged resources

data/
  manifests/              # Source manifests
  parsed/                 # Section-level parsed artifacts
  processed/              # Chunk, embedding, and index artifacts

docs/
  adr/                    # Architecture decisions
  data/                   # Corpus and licensing docs
  diagrams/               # Architecture / ingestion diagrams
  process/                # Repo workflow and governance docs
```

---

## 6. Corpus and Licensing

The current MVP corpus is a pinned Kubernetes documentation snapshot. Corpus governance, allowlist rules, and licensing decisions are documented in `docs/data/corpus.md` and the ADRs under `docs/adr/`.

---

## 7. Local Development

### Base environment

For normal repo development:

```bash
uv sync --locked --extra dev-tools
```

### Embedding job dependencies

For local embedding work, install the optional embedding dependencies too:

```bash
uv sync --locked --extra dev-tools --extra embeddings-local
```

### FAISS index dependencies

For local FAISS index work, install the FAISS extra:

```bash
uv sync --locked --extra dev-tools --extra faiss
```

If you want to run both the local embedding job and the local FAISS backend on the same machine, install both extras together:

```bash
uv sync --locked --extra dev-tools --extra embeddings-local --extra faiss
```

### Run the embedding job

After you have `data/processed/chunks.jsonl`, run:

```bash
uv run python -m supportdoc_rag_chatbot embed-chunks \
  --input data/processed/chunks.jsonl \
  --vectors-output data/processed/embeddings/chunk_embeddings.f32 \
  --metadata-output data/processed/embeddings/chunk_embeddings.metadata.json \
  --model-name sentence-transformers/all-MiniLM-L6-v2
```

Useful options:

- `--device cpu|cuda|mps`
- `--batch-size 32`
- `--no-normalize`

### Build the local FAISS index

After the embedding artifacts exist, build the persisted FAISS index:

```bash
uv run python -m supportdoc_rag_chatbot build-faiss-index \
  --embedding-metadata data/processed/embeddings/chunk_embeddings.metadata.json \
  --index-output data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata-output data/processed/indexes/faiss/chunk_index.metadata.json \
  --row-mapping-output data/processed/indexes/faiss/chunk_index.row_mapping.json
```

### Load the saved FAISS backend from Python

```python
from pathlib import Path

from supportdoc_rag_chatbot.retrieval.indexes import load_faiss_index_backend

backend = load_faiss_index_backend(
    index_path=Path("data/processed/indexes/faiss/chunk_index.faiss"),
    metadata_path=Path("data/processed/indexes/faiss/chunk_index.metadata.json"),
)
```

### Run a local dense-retrieval smoke test

After the FAISS index exists, run a query end to end:

```bash
uv run python -m supportdoc_rag_chatbot smoke-dense-retrieval \
  --query "what is a pod" \
  --top-k 3 \
  --index data/processed/indexes/faiss/chunk_index.faiss \
  --index-metadata data/processed/indexes/faiss/chunk_index.metadata.json
```

By default, the smoke command:

- loads the embedding model recorded in the FAISS index metadata,
- uses the row-mapping path recorded in the index metadata,
- uses the source `chunks.jsonl` path recorded in the index metadata, and
- prints rank, score, chunk ID, section path, source URL, and a short text preview.

Useful options:

- `--row-mapping data/processed/indexes/faiss/chunk_index.row_mapping.json`
- `--chunks data/processed/chunks.jsonl`
- `--model-name sentence-transformers/all-MiniLM-L6-v2`
- `--device cpu|cuda|mps`
- `--preview-chars 200`

### Local verification

Run lint and tests:

```bash
uv run ruff check . --no-fix
uv run ruff format --check .
uv run pytest -q
```

---

## 8. Citations and Refusal Behavior

The target product behavior is to answer only when retrieved evidence is sufficient and attributable. Citation validation and refusal rules are still being layered into the backend pipeline, but the repository structure already separates retrieval, generation, and trust-layer concerns so those checks can be added incrementally.

---

## 9. Evaluation Plan / Results

Evaluation work is planned in two stages:

1. retrieval smoke tests and baseline relevance checks,
2. end-to-end answer quality, citation support, and refusal correctness.

Results will be documented under the evaluation package and in future project reports as those baselines are implemented.

---

## 10. Deployment Overview

The intended deployment path is a FastAPI backend with a web frontend, persistent artifact storage, a vector retrieval layer, and a replaceable generation backend. The local MVP keeps artifacts simple so the deployment architecture can evolve without rewriting the ingestion or embedding steps.

---

## 11. Documentation Map / Roadmap

- `docs/process/git_workflow.md` — branch / PR / lockfile workflow
- `docs/data/corpus.md` — corpus scope and licensing notes
- `docs/diagrams/ingestion_pipeline.md` — ingestion pipeline overview
- `docs/adr/` — architecture decisions and project rationale
- `PROPOSAL.md` — project proposal and delivery framing
