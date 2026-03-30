# MVP readiness report (Epic 10)

## Overall status

**Current decision for this repository snapshot:** **not ready to close Epic 10 yet**.

This report is the source-of-truth closeout artifact for final-readiness review in the current ZIP. It summarizes what is already evidenced in the repository, what is still missing, and which Epic 10 items still block closure.

Use this page as the first stop for MVP-readiness review. Historical planning documents such as `PROPOSAL.md` remain useful context, but they are not the operational source of truth for final validation.

## Readiness matrix

| Readiness item | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Fixture-mode API smoke | PASS | [`README.md` §7A](../../README.md#7a-local-api-smoke-workflow), [`scripts/run-api-local.sh`](../../scripts/run-api-local.sh), [`tests/test_local_api_workflow.py`](../../tests/test_local_api_workflow.py), [`.github/workflows/test.yml`](../../.github/workflows/test.yml) | Deterministic local API smoke exists for `/healthz`, `/readyz`, and fixture-backed `/query`. |
| Container runtime smoke | FAIL | [`README.md` §7B](../../README.md#7b-containerized-local-api-smoke-workflow), [`docker/backend.Dockerfile`](../../docker/backend.Dockerfile), [`docker-compose.yml`](../../docker-compose.yml), [`tests/test_container_packaging.py`](../../tests/test_container_packaging.py) | Container packaging and manual run steps are documented, but this ZIP does not include a committed runtime-smoke script, runtime-smoke test, or reviewed runtime-smoke artifact. |
| Artifact-mode API smoke | FAIL | [`README.md` artifact mode note](../../README.md#artifact-mode), [`tests/test_local_api_workflow.py`](../../tests/test_local_api_workflow.py) | Artifact-mode startup preflight exists, but this ZIP does not include a deterministic artifact fixture, artifact-mode smoke wrapper, or artifact-backed HTTP smoke evidence. |
| Final evidence review package | FAIL | [`data/evaluation/`](../../data/evaluation/), [`docs/process/retrieval_dev_qa.md`](../../docs/process/retrieval_dev_qa.md) | The retrieval-only Dev QA set exists, but the final end-to-end evidence review set, reviewer rubric, and blank review-results template are not committed in this ZIP. |
| Evidence correctness pass | FAIL | [`docs/contracts/query_response.schema.json`](../../docs/contracts/query_response.schema.json), [`docs/process/citation_validator.md`](../../docs/process/citation_validator.md), [`docs/process/refusal_response_builder.md`](../../docs/process/refusal_response_builder.md) | Trust-building pieces exist, but this ZIP does not include reviewed first-pass/final-pass artifacts or a recorded reviewed sample for the final evidence correctness pass. |
| Repo polish / source-of-truth cleanup | FAIL | [`README.md`](../../README.md), [`docs/data/corpus.md`](../../docs/data/corpus.md), [`docs/adr/`](../../docs/adr), [`docs/architecture/aws_deployment.md`](../../docs/architecture/aws_deployment.md) | The repo is navigable, but final validation/readiness landing pages and the last source-of-truth cleanup pass are not committed in this ZIP. |
| AWS baseline cost/ops notes (#78) | FAIL | [`docs/architecture/aws_deployment.md`](../../docs/architecture/aws_deployment.md) | The AWS deployment architecture note exists, but the dedicated baseline cost/ops note requested by Epic 10 is not committed in this ZIP. |
| Container build smoke in CI (#79) | FAIL | [`.github/workflows/test.yml`](../../.github/workflows/test.yml), [`tests/test_container_packaging.py`](../../tests/test_container_packaging.py) | CI runs lint and pytest, but this ZIP does not include a committed Docker image build smoke job. |

## Evidence details by item

### Fixture-mode API smoke

**Canonical local command**

```bash
./scripts/run-api-local.sh
```

**Why this is considered ready in the current ZIP**

- the startup wrapper is committed under `scripts/run-api-local.sh`
- `README.md` documents the canonical fixture-mode path and example HTTP calls
- `tests/test_local_api_workflow.py` covers `/healthz`, `/readyz`, and fixture-backed `/query`
- the normal pytest workflow in `.github/workflows/test.yml` executes that test coverage in CI

### Container runtime smoke

**Current repo evidence**

```bash
docker build -f docker/backend.Dockerfile -t supportdoc-rag-chatbot-api:local .
docker compose up --build -d
docker compose ps
```

The current ZIP proves that the backend is packaged for container use and that the local manual smoke sequence is documented. It does **not** yet prove final-readiness runtime validation because there is no committed runtime-smoke wrapper, no committed runtime-smoke test, and no committed reviewed runtime artifact.

### Artifact-mode API smoke

**Current repo evidence**

```bash
SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh
```

The current ZIP proves that artifact-mode startup is conceptually supported and that missing artifacts fail fast. It does **not** yet include the deterministic artifact fixture and self-contained artifact-mode API smoke suite that Epic 10 expects for closure.

### Final evidence review package

This ZIP already contains retrieval-only evaluation assets under `data/evaluation/` plus the supporting process docs under `docs/process/`, but it does **not** yet contain the separate final evidence review package for end-to-end API review. The following expected artifacts are missing in this snapshot:

- a versioned final evidence review question set
- a reviewer rubric for citation/refusal judgment
- a blank review-results template
- a stable validation-doc landing page for reviewed outputs

### Evidence correctness pass

The current ZIP includes the trust-layer schema plus process docs for citation validation and refusal behavior, but it does **not** include the reviewed evidence-correctness artifacts needed to close the epic, such as:

- a first-pass reviewed output artifact
- a final-pass reviewed output artifact
- a summary of blocker fixes between passes
- a committed final summary showing citation correctness and refusal correctness for the reviewed sample

### Repo polish / source-of-truth cleanup

This report intentionally treats the attached ZIP as the source of truth. On that basis, the repository still needs the final polish pass expected by Epic 10. In particular, the current snapshot does not yet present one clear final-validation landing page from the repo root, and it still reads as a project mid-flight rather than a fully closed MVP readiness package.

### AWS baseline cost/ops notes (#78)

The repo contains `docs/architecture/aws_deployment.md`, which is useful architecture guidance, but the dedicated cost/ops baseline note requested by Epic 10 is not committed in this ZIP.

### Container build smoke in CI (#79)

The repo already has container packaging documentation and tests that assert the Dockerfile/Compose path is documented, but the GitHub Actions workflows in this ZIP run lint and pytest only. They do not include an explicit Docker build smoke job.

## Known limitations and deferred scope

These points are still open or explicitly deferred in the current ZIP and should stay visible in readiness review:

- artifact-mode container support is explicitly deferred in `README.md`
- no frontend application is committed in this ZIP; the repo remains API-first
- AWS deployment architecture is documented, but AWS baseline cost/ops notes are not yet committed
- container packaging exists, but runtime-smoke and build-smoke evidence are not yet committed as final-readiness artifacts
- end-to-end evidence review materials and reviewed evidence-correctness outputs are not yet committed in this snapshot

## Closure checklist for Epic 10

Use this checklist directly when deciding whether Epic 10 can close for the current repository snapshot.

- [x] Fixture-mode API smoke path is committed and documented from the repo root.
- [ ] Container runtime smoke is committed as a readiness-grade workflow with supporting evidence.
- [ ] Artifact-mode API smoke is committed as a deterministic end-to-end workflow.
- [ ] Final evidence review package is committed in a stable repo location.
- [ ] Evidence correctness pass is reviewed, recorded, and free of blocker-level defects.
- [ ] Repo polish / source-of-truth cleanup is complete.
- [ ] AWS baseline cost/ops notes (#78) are committed.
- [ ] Container build smoke in CI (#79) is committed.
- [x] Final MVP readiness report / closure checklist (#92) is committed.

## Epic 10 task map

| Epic 10 task | Status in this ZIP | Notes |
| --- | --- | --- |
| Add cost and ops notes for the AWS baseline (#78) | OPEN | `docs/architecture/aws_deployment.md` exists, but the dedicated cost/ops note is missing. |
| Add container build smoke check to CI (#79) | OPEN | No Docker build job is committed under `.github/workflows/`. |
| Add fixture-mode API E2E smoke suite | DONE | Covered by `scripts/run-api-local.sh`, README §7A, and `tests/test_local_api_workflow.py`. |
| Add container runtime smoke validation | OPEN | Packaging docs exist, but readiness-grade runtime-smoke evidence is missing. |
| Add artifact-mode API E2E smoke suite | OPEN | Artifact-mode preflight exists; deterministic smoke suite is missing. |
| Add final evidence review set and review rubric | OPEN | Retrieval-only Dev QA exists; final review package is missing. |
| Run evidence correctness pass and fix validation blockers | OPEN | Reviewed final-pass evidence artifacts are missing. |
| Repo polish and source-of-truth cleanup | OPEN | Final documentation cleanup pass is not fully represented in this ZIP. |
| Publish final MVP readiness report and closure checklist (#92) | DONE | This document. |

## Final closeout call

**Do not close Epic 10 on this repository snapshot yet.**

This ZIP already supports fixture-mode API smoke and has credible building blocks for the remaining readiness tasks, but it does not yet include the artifact-backed validation package and closing evidence required to claim final MVP readiness.
