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
- a thin local browser demo now exists under `frontend/` and can call the live local API, but browser smoke remains outside this validation index,
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
- `docs/process/retrieval_comparison_notes.md` — retrieval-only baseline comparison and provisional hybrid recommendation

## Readiness-report location

This directory is also the canonical home for the final Epic 10 closeout artifact. When the MVP readiness report is published, it should live alongside the files above so reviewers can find smoke proofs and reviewed trust evidence from one place.
