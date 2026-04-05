# Report-facing notes and AWS handoff notes for the UI layer

This note is the source-of-truth summary for two follow-on tasks: updating the final report and keeping the later AWS deployment epic aligned with the same UI/backend boundary.

## Baseline answer for “training process (if applicable)”

The baseline SupportDoc RAG Chatbot does **not** require fine-tuning.

Use this wording in the report:

> The baseline system does not perform model fine-tuning or custom weight updates. It uses pretrained components for embeddings and answer generation, then grounds responses with retrieval, citation validation, and structured refusal behavior. For this project, the relevant preparation work is data and retrieval preparation rather than model training.

That is the project’s canonical answer to the “training process (if applicable)” requirement: **no fine-tuning is required for the baseline**.

## Baseline preparation and indexing flow

The real baseline preparation flow is:

**snapshot -> parse -> chunk -> embed -> index**

Use this wording in the report:

> The baseline system is prepared from a pinned documentation snapshot rather than from a fine-tuning dataset. The allowlisted corpus snapshot is recorded in the source manifest, parsed into structured sections, split into provenance-preserving chunks, embedded into dense vectors, and loaded into a retrieval index. Query-time answers are generated against that indexed evidence and validated before the response is returned.

The repo-level mapping for that flow is:

1. **snapshot** — pin the approved documentation snapshot and manifest under `data/manifests/` as described in `docs/data/corpus.md`
2. **parse** — convert approved source files into section-level artifacts under `data/parsed/`
3. **chunk** — write provenance-preserving chunks under `data/processed/chunks.jsonl`
4. **embed** — generate dense vector artifacts under `data/processed/embeddings/`
5. **index** — build the retrieval index used at query time (FAISS locally today, `pgvector` in the AWS target path)

This is the baseline preparation story for the report. It explains how the system is actually prepared for the domain without implying that the model itself was retrained.

## UI implementation notes for the final report

Use this wording in the report’s UI implementation section:

> The UI layer is intentionally thin. A React SPA collects the user question, sends it to the FastAPI backend, and renders either a citation-backed answer or a structured refusal returned by the backend. Retrieval, generation, citation validation, refusal policy, and evidence-sufficiency decisions remain in the backend so the browser does not become a second source of truth.

For the report, describe the UI responsibilities as:

- collect the user question and show request state
- call the backend contract (`/query`, `/healthz`, and `/readyz` as needed)
- render the final answer, citations, or refusal returned by the backend
- keep secrets, retrieval settings, model settings, and trust logic out of the browser

## Local versus AWS handoff notes for the UI layer

The local and AWS stories should describe the same architecture boundary, not two different applications.

### Local baseline

- The current repo is still **API-first** and validates the backend shell locally.
- When the browser UI is used locally, it should stay a thin client over the same FastAPI contract.
- The local backend starts with `./scripts/run-api-local.sh` and defaults to fixture mode for deterministic smoke testing.
- Local artifact mode remains optional and depends on `chunks.jsonl` plus the FAISS artifact set.
- A local browser client should need only the backend base URL; it should not own retrieval or generation configuration.

### AWS handoff direction

- Keep the **React + FastAPI** split already established in `PROPOSAL.md` and `docs/architecture/aws_deployment.md`.
- Host the React SPA on **AWS Amplify Hosting** later.
- Keep the FastAPI backend behind an **ALB + ECS Fargate** service.
- Keep retrieval, generation, refusal policy, and citation validation in the backend API.
- Keep the inference host and retrieval backend private to the backend tier.
- Keep browser-visible runtime configuration limited to the public API base URL and non-secret UI labels.

## UI-layer AWS handoff rules

The future AWS deployment epic should preserve these rules:

1. the browser remains a presentation layer, not a trust layer
2. the backend remains the single source of truth for supported answers and refusals
3. Secrets Manager and SSM Parameter Store stay backend-only concerns
4. the browser never receives direct database credentials, inference credentials, or artifact paths
5. moving from local to AWS changes the hosting path, not the answer/refusal contract

## Short report-ready summary

For a concise final report summary, use this paragraph:

> The baseline SupportDoc RAG Chatbot does not rely on fine-tuning. Instead, it prepares a pinned documentation snapshot through a retrieval-first pipeline: snapshot, parse, chunk, embed, and index. The UI layer is intentionally thin and delegates retrieval, generation, citation validation, and refusal behavior to the FastAPI backend. Locally, the system is validated through the backend-first workflow; in the AWS target architecture, the same backend contract is retained while the React SPA is hosted separately and calls the backend over HTTP.
