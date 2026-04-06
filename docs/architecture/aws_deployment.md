# AWS Deployment Architecture

This document is the single baseline AWS deployment reference for the current API-first repository state and the target capstone deployment.

It does two things:

1. records what exists in the repo today,
2. defines one default AWS deployment path for the capstone MVP.

The baseline is intentionally opinionated so later infra work can build against one path instead of several equal alternatives.

Companion cost and operations notes for the same baseline live in `docs/ops/cost_and_ops.md`.

The runtime / trust validation entry point for this same API-first MVP lives in `docs/validation/README.md`.

Report-facing UI wording and the later browser-to-AWS handoff notes live in `docs/validation/report_and_aws_handoff_notes.md`.

## Baseline decision summary

The capstone MVP will use this default AWS path:

- **API hosting:** Amazon ECS on Fargate running the FastAPI backend behind an Application Load Balancer (ALB)
- **Inference hosting:** one private EC2 GPU instance running the HTTP generation backend (vLLM or TGI)
- **Vector store / retrieval backend:** Amazon RDS for PostgreSQL with `pgvector`
- **Object storage:** Amazon S3 for corpus snapshots, processed artifacts, and evaluation outputs
- **Logging / metrics:** CloudWatch Logs plus CloudWatch metrics and alarms
- **Secrets / config:** AWS Secrets Manager for secrets and Systems Manager Parameter Store for non-secret runtime configuration
- **Browser hosting:** AWS Amplify Hosting for the checked-in React SPA when the separate browser-hosting slice is enabled

This baseline matches the proposal's intended deployment direction while staying explicit about what is already implemented in the repo versus what is still deferred. The browser layer stays aligned to the same React + FastAPI split described in `docs/validation/report_and_aws_handoff_notes.md`.

## Current repo state

The current repository is **API-first**, not full-stack yet.

What already exists in the ZIP:

- FastAPI backend shell with `/healthz`, `/readyz`, and `/query`
- deterministic local startup path via `scripts/run-api-local.sh`
- retrieval modes for local fixture flow and local artifact-backed flow
- local retrieval artifacts built around `chunks.jsonl` plus FAISS index files
- canonical trust-layer response schema and smoke validation
- structured backend orchestration for retrieval, refusal gating, generation, and citation validation

What is available now for the UI layer:

- a checked-in React SPA scaffold under `frontend/` for the thin local browser demo

What does **not** exist yet in the ZIP:

- a committed AWS service definition or infrastructure-as-code stack
- a production-ready hosted frontend deployment
- a cloud retrieval adapter for `pgvector`
- a production inference adapter that talks directly to raw vLLM / TGI responses
- dependency-aware `/readyz` checks for cloud services

That means the repo can already support a **deploy-now backend shell on AWS** and the browser configuration boundary for a later separate frontend origin, but not the full target stack yet.

## Deploy-now scope

The deploy-now scope is the smallest AWS slice that matches the current repo reality.

It is a subset of the baseline path:

- deploy the FastAPI backend to ECS Fargate
- keep the public entry point at an ALB
- wire CloudWatch logging and basic ECS / ALB health monitoring
- store deployment-time artifacts and future ingestion outputs in S3
- keep retrieval and generation in fixture mode unless a compatible backend contract is wired explicitly

For immediate deployment readiness, the backend can start in **fixture mode** and prove:

- bootability from a clean image
- deterministic `/healthz` and `/readyz` responses
- a stable `/query` contract
- log capture and operational visibility

Those proofs are exercised locally with `./scripts/smoke-container-runtime.sh` and the reviewed trust artifacts grouped under `docs/validation/`.

This is the shortest path from the current repo to an AWS-hosted backend shell.

### First browser-backed AWS slice

The first browser-backed slice keeps the same backend shell and adds the checked-in React SPA as a separately hosted client.

That slice requires only three additional rules:

- host the SPA separately, for example on Amplify Hosting
- set `VITE_SUPPORTDOC_API_BASE_URL` to the public backend origin
- set explicit backend CORS policy through `SUPPORTDOC_API_CORS_ALLOWED_ORIGINS` and/or `SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX`

The backend keeps safe localhost browser access by default. When `SUPPORTDOC_DEPLOYMENT_TARGET=aws` is selected, the app now fails fast unless a non-local browser origin policy is configured explicitly.

## Target capstone baseline

The target capstone deployment uses the same API-first backend, but upgrades the runtime dependencies to a production-style AWS layout.

### Component-to-service mapping

| Concern | Baseline AWS service | Baseline decision |
| --- | --- | --- |
| API hosting | ECS Fargate + ALB | Run the FastAPI backend as a containerized service with one public HTTP entry point |
| Inference hosting | EC2 GPU instance | Host one private inference server (vLLM or TGI) behind the API over internal HTTP |
| Vector store / retrieval backend | RDS PostgreSQL + `pgvector` | Use one managed relational/vector backend instead of keeping local FAISS files in production |
| Object storage | S3 | Store corpus snapshots, processed artifacts, evaluation outputs, and deployment-time reference files |
| Logging / metrics | CloudWatch Logs, CloudWatch metrics, CloudWatch alarms | Keep structured application logs and basic service health telemetry in one place |
| Secrets / config | Secrets Manager + SSM Parameter Store | Keep credentials, endpoint tokens, and runtime configuration outside the container image |
| Browser hosting | Amplify Hosting | Host the checked-in React SPA separately without changing the backend deployment path |

### Networking assumptions

The baseline assumes one VPC with public and private subnets:

- **public subnet:** ALB only
- **private subnets:** ECS tasks, RDS PostgreSQL, and the EC2 GPU inference instance
- **security groups:**
  - ALB accepts public HTTPS traffic
  - ECS accepts traffic only from the ALB
  - RDS accepts traffic only from the ECS service
  - EC2 inference accepts traffic only from the ECS service

The vector store and inference host are not publicly reachable.

## UI layer handoff notes

The current repo stays **API-first**, but the UI direction is already fixed: keep a thin React SPA in front of the FastAPI backend instead of moving trust logic into the browser.

The handoff boundary is:

- **browser-owned:** question input, loading/error state, answer/refusal rendering, and citation display
- **backend-owned:** retrieval, generation, citation validation, refusal policy, and runtime secrets/config

For local use, the browser should call the same FastAPI contract that the current repo already validates (`/query`, `/healthz`, and `/readyz`). For AWS, the same contract should stay behind the ALB/ECS service while the React SPA is hosted separately on Amplify.

Use `docs/validation/report_and_aws_handoff_notes.md` when you need report-ready wording for this same UI/backend split.

## Runtime configuration contract

For AWS, keep one explicit runtime split so the container does not rely on repo-local defaults.

### Non-secret values: ECS task environment variables or SSM Parameter Store

| Setting | Why it exists | Deploy-now expectation |
| --- | --- | --- |
| `SUPPORTDOC_DEPLOYMENT_TARGET` | Distinguish local default behavior from the AWS-targeted runtime path | Set to `aws` in AWS environments |
| `SUPPORTDOC_ENV` | Human-readable environment label surfaced by `/readyz` | Set to the intended stage name |
| `SUPPORTDOC_API_CORS_ALLOWED_ORIGINS` | Explicit browser-origin allowlist for separately hosted frontend origins | Required for the first browser-backed AWS slice unless a regex is used instead |
| `SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX` | Regex-based browser-origin policy when one exact origin is not enough | Optional alternative to the explicit allowlist |
| `SUPPORTDOC_QUERY_RETRIEVAL_MODE` | Choose the retrieval path | `fixture` for the deploy-now backend shell; `artifact` remains local-only in the current repo |
| `SUPPORTDOC_QUERY_GENERATION_MODE` | Choose the generation path | `fixture` for the deploy-now backend shell; `http` only when a compatible backend contract exists |
| `SUPPORTDOC_QUERY_GENERATION_BASE_URL` | Backend generation endpoint location | Required only when `SUPPORTDOC_QUERY_GENERATION_MODE=http` |
| `VITE_SUPPORTDOC_API_BASE_URL` | Browser-visible API origin used by the SPA | Set in Amplify Hosting to the public backend origin |

### Secret values: Secrets Manager

Keep only genuinely sensitive runtime inputs in Secrets Manager, such as:

- database credentials
- inference tokens or private gateway credentials if they are added later
- any later third-party API credentials

The current deploy-now backend shell does not require a database secret or inference secret because fixture mode is the intended first AWS slice.

## Request flow

### Deploy-now backend shell / first browser-backed slice

The request path that is actually supported now is:

1. the user calls the backend API directly now, or through the separately hosted React SPA later,
2. the ALB forwards the request to the ECS Fargate FastAPI service,
3. the API validates the request and loads runtime configuration,
4. the API runs fixture-mode retrieval/generation now, or a compatible HTTP generation backend if one is configured explicitly,
5. the API validates the response against the trust-layer contract,
6. the API returns either a citation-backed answer or a structured refusal.

### Future cloud retrieval / inference target

The request path for the full target architecture is:

1. the user calls the backend API directly now, or through the future React frontend later,
2. the ALB forwards the request to the ECS Fargate FastAPI service,
3. the API validates the request and loads runtime configuration,
4. the API queries the `pgvector` retrieval backend in RDS for ranked evidence,
5. the API sends the question plus retrieved evidence to the private inference server,
6. the API validates the generated response against the trust-layer contract,
7. the API returns either a citation-backed answer or a structured refusal.

This keeps orchestration, validation, and refusal enforcement in the backend API instead of distributing those responsibilities across multiple services.

## Artifact flow

The artifact flow for the baseline deployment is:

1. the allowlisted corpus snapshot is stored in S3,
2. ingestion outputs such as parsed sections, chunks, embeddings, and evaluation artifacts are versioned in S3,
3. the promoted retrieval dataset is loaded into PostgreSQL + `pgvector`,
4. the runtime API reads only the data it needs for query-time retrieval,
5. evaluation runs write summary artifacts back to S3 for later review.

The current repo still produces local artifacts first. The AWS baseline does not replace that local workflow; it defines how those artifacts are promoted into cloud storage and a managed retrieval backend later. The code in this ZIP does **not** yet include the runtime adapter that queries `pgvector` directly.

## Health, readiness, and failure boundaries

### Health and readiness

The current backend already exposes:

- **`/healthz`** for process liveness
- **`/readyz`** for deterministic API readiness metadata

In the baseline deployment:

- ECS / ALB health checks should use **`/healthz`** for restart and routing decisions
- **`/readyz`** remains the operator-facing readiness endpoint for deployment smoke tests and release checks
- the ALB target-group health path should stay on `/healthz`, not on `/readyz`

Important current limitation:

- the current `/readyz` route reports deterministic application readiness metadata
- it does **not** yet perform deep dependency checks against RDS, S3, or the inference server

That means dependency loss is still detected primarily through:

- failed `/query` requests
- ECS / ALB task health
- CloudWatch logs and service alarms

### Failure boundaries

The baseline failure boundaries are:

- **ALB / ECS boundary:** if the API container stops responding, ECS replaces the task
- **API to RDS boundary:** retrieval failure should fail the request and surface a controlled API error rather than returning unsupported content
- **API to inference boundary:** generation failure should fail closed and preserve refusal / validation guarantees
- **S3 artifact boundary:** artifact upload or promotion failures should block data refresh, not silently mutate the live query path

This preserves one important rule: **the API should fail closed rather than degrade into uncited answers.**

## Observability touchpoints

The baseline observability posture is intentionally small and practical:

- structured JSON logs from the FastAPI service
- ALB request metrics
- ECS service metrics (task count, CPU, memory, restart events)
- RDS health metrics (availability, connections, storage, CPU)
- EC2 inference host health metrics (CPU/GPU utilization, memory, restart events)
- application-level counters or logs for:
  - request latency
  - retrieval mode / backend
  - top-k retrieval diagnostics
  - refusal reason codes
  - citation validation failures

Optional OpenTelemetry tracing is deferred. CloudWatch-first logging is the default path for the capstone MVP.

## Current state vs deployable MVP vs deferred options

### Current repo state

- API-first backend exists
- checked-in React SPA scaffold exists under `frontend/`
- local fixture and artifact retrieval flows exist
- local FAISS artifacts are the current retrieval baseline
- container packaging and local container smoke exist
- no committed AWS service definitions exist yet

### Deployable MVP scope

- ECS Fargate API service
- ALB ingress
- CloudWatch logging / metrics
- S3 for versioned artifacts
- fixture-mode backend shell now
- separate browser hosting through the existing SPA plus `VITE_SUPPORTDOC_API_BASE_URL` and explicit CORS policy when that slice is enabled

### Deferred / stretch options

These options are intentionally **not** part of the default baseline:

- `pgvector` runtime retrieval integration in the API code
- production inference adapter work for raw vLLM / TGI responses
- OpenSearch Serverless or managed OpenSearch as the retrieval backend
- SageMaker real-time inference endpoints
- API Gateway + Lambda streaming as the primary backend path
- full OpenTelemetry tracing stack
- autoscaling policies beyond a small baseline service

## Open questions and deferred decisions

The following points still need explicit implementation decisions in later infra tasks:

1. **Inference server choice:** vLLM vs TGI for the first EC2 GPU deployment
2. **Retrieval promotion job:** whether `pgvector` loading happens from a one-off script, ECS task, or CI/CD step
3. **Artifact promotion path:** which exact S3 prefixes become the stable handoff points for deployment-ready data
4. **Frontend cutover timing:** whether the capstone demo initially ships API-only or with the React frontend enabled
5. **Dependency-aware readiness:** whether `/readyz` should grow deep checks for RDS and inference before final deployment

## Diagram source

The versioned Mermaid source for this deployment lives in:

- `docs/diagrams/aws_deployment.mmd`
