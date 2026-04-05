# Validation Index

This directory is the source-of-truth landing page for **API-first MVP validation**.

Use it when you want to answer these questions quickly:

- what is the canonical local API smoke path?
- what is the canonical artifact-mode smoke path?
- what is the canonical packaged container runtime smoke path?
- where is the reviewed evidence package for the MVP trust pass?

The current validated scope is intentionally **backend / API first**:

- fixture-mode local API smoke is supported,
- artifact-mode local API smoke is supported,
- backend container runtime smoke is supported in fixture mode,
- reviewed evidence correctness artifacts are committed,
- thin local browser scaffold now exists under `frontend/`,
- artifact-mode inside the container image remains deferred.

## Canonical commands

### Fixture-mode local API smoke

Boot the local API with deterministic fixture responses:

```bash
./scripts/run-api-local.sh
```

Docs: `README.md` section `7A. Local API Smoke Workflow`

### Artifact-mode API smoke

Run the deterministic artifact-backed API smoke suite:

```bash
./scripts/smoke-artifact-api.sh
```

This path creates a temporary artifact fixture, starts the backend in artifact mode, validates `/healthz`, `/readyz`, and supported + refusal `/query` responses, then cleans up.

Docs: `README.md` section `7A. Local API Smoke Workflow`

### Container runtime smoke

Run the packaged backend runtime smoke path:

```bash
./scripts/smoke-container-runtime.sh
```

This path builds the checked-in backend image, starts it with `docker run`, waits for health, validates `/healthz`, `/readyz`, and supported + refusal `/query` responses, then cleans up.

Docs: `README.md` section `7B. Containerized Local API Smoke Workflow`

### Trust-contract schema smoke

Validate the canonical `QueryResponse` fixtures against the committed schema:

```bash
uv run python -m supportdoc_rag_chatbot smoke-trust-schema \
  --schema docs/contracts/query_response.schema.json \
  --answer-fixture docs/contracts/query_response.answer.example.json \
  --refusal-fixture docs/contracts/query_response.refusal.example.json
```

Docs: `docs/process/trust_response_contract.md`

## Reviewed evidence package

The final MVP trust pass is documented with these committed artifacts:

- `data/evaluation/final_evidence_review.k8s-9e1e32b.v1.jsonl` — versioned review set
- `data/evaluation/final_evidence_review.k8s-9e1e32b.v1.metadata.json` — review-set metadata
- `docs/validation/final_evidence_review_rubric.md` — reviewer rubric
- `docs/validation/final_evidence_review_results.template.md` — blank review template
- `docs/validation/final_evidence_review.first_pass.raw.json` — first reviewed pass raw outputs
- `docs/validation/final_evidence_review.final_pass.raw.json` — final reviewed pass raw outputs
- `docs/validation/final_evidence_review.md` — reviewed evidence summary and known limitations

## Related source-of-truth docs

- `README.md` — repo overview, local workflows, validation entry points, and deployment framing
- `docs/data/corpus.md` — corpus snapshot and corpus-governance contract
- `docs/architecture/aws_deployment.md` — canonical AWS baseline and deferred scope labels
- `docs/validation/report_and_aws_handoff_notes.md` — report-ready notes for the no-fine-tuning baseline, retrieval preparation flow, and UI/AWS handoff
- `docs/process/retrieval_comparison_notes.md` — retrieval-only baseline comparison and provisional hybrid recommendation

## Readiness-report location

This directory is also the canonical home for the final Epic 10 closeout artifact. When the MVP readiness report is published, it should live alongside the files above so reviewers can find smoke proofs and reviewed trust evidence from one place.


## Browser demo docs and smoke path

The combined fixture-mode browser-demo smoke path is the canonical operator-facing browser check for the current local demo layer.

Run it from the repo root:

```bash
bash scripts/smoke-browser-demo.sh
```

This path starts `./scripts/run-api-local.sh`, checks one supported answer in canonical fixture mode, then builds and serves the browser assets long enough to confirm the thin local browser scaffold now exists under `frontend/` and boots against the local backend.

Use these companion docs together:

- `docs/validation/browser_smoke_checklist.md` — manual browser smoke checklist with a supported answer in canonical fixture mode, refusal, empty-input, backend-unavailable, and long-answer visual checks
- `docs/validation/local_workflow_platforms.md` — macOS arm64 / Pop!_OS x86_64 setup notes, Python 3.13 baseline, and artifact prerequisites
- `README.md` sections `2A. Demo day quick start` and `7C. Local browser demo` — canonical first-run path and local browser scaffold notes
- `frontend/README.md` — browser startup, `POST /query` wiring, and `/readyz` status probe details
