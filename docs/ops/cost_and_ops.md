# AWS Cost and Ops Notes

This document is the practical operations companion to `docs/architecture/aws_deployment.md`.

It keeps one goal in focus: make the chosen AWS baseline believable and operable for a capstone demo without pretending this is a full production platform.

For report-ready UI wording and the local-browser-demo to AWS handoff notes that match this same baseline, see `docs/validation/report_and_aws_handoff_notes.md`.

These notes are intentionally directional rather than price-quote accurate. They describe the expected cost shape, the services that matter most, and the smallest set of operational checks needed to run the baseline safely.

## Scope and baseline alignment

This note matches the current baseline defined in `docs/architecture/aws_deployment.md`:

The concrete Task 1 implementation and its exact env/secret naming contract live in `infra/aws/task1-foundation/` and `docs/ops/aws_task1_foundation.md`.

- **API hosting:** ECS Fargate behind an ALB
- **Inference hosting:** one private EC2 GPU instance
- **Vector store / retrieval backend:** RDS PostgreSQL with `pgvector`
- **Object storage:** S3
- **Logging / metrics:** CloudWatch
- **Secrets / config:** Secrets Manager plus SSM Parameter Store
- **Browser hosting:** Amplify Hosting for the checked-in SPA when the separate browser-hosting slice is enabled

The working assumption for planning is one U.S. commercial AWS region, now pinned to **`us-west-2` for the MVP foundation** so the networking, HTTPS edge, and runtime config naming stay consistent across later tasks.

## Operating modes

This repo now has two practical operating postures for infra planning:

### Demo-hours posture (default capstone posture)

Use this mode for milestone demos, instructor reviews, and short evaluation windows.

Characteristics:

- one small ECS service for the API
- one ALB
- one small RDS PostgreSQL instance
- one private EC2 GPU inference host started only for active demo or testing windows
- short CloudWatch retention
- minimal alarms and no aggressive autoscaling

This is the default operational stance for the capstone because it keeps the architecture real while limiting idle spend.

### Always-on posture (limited integration posture)

Use this mode only during concentrated integration, performance testing, or final validation windows.

Characteristics:

- API, ALB, RDS, and inference host remain on continuously
- CloudWatch retention is longer
- alarms stay enabled at all times
- operational convenience improves, but compute costs rise quickly

This posture is useful for short periods, but it should not be the default outside final integration or demo week.

## UI-layer configuration boundary

The frontend remains a thin client in both local and AWS stories. That means the browser should carry only public UI configuration, such as `VITE_SUPPORTDOC_API_BASE_URL` and non-secret environment labels.

The browser must not receive:

- database credentials
- inference credentials
- artifact paths
- retrieval tuning values that are meant to stay backend-only

This keeps the React + FastAPI split aligned with the baseline AWS plan and prevents the UI layer from becoming a second operational control plane.

## Baseline service assumptions

| Layer | Baseline service | Planning assumption |
| --- | --- | --- |
| Public entry point | ALB | One HTTPS entry point in front of the FastAPI service |
| API runtime | ECS Fargate | One small backend task, scale out deferred |
| Inference | EC2 GPU | One private inference host; no managed endpoint in the baseline |
| Retrieval | RDS PostgreSQL + `pgvector` | One managed relational/vector instance; no OpenSearch in the baseline |
| Artifact storage | S3 | Versioned corpus snapshots, processed artifacts, and evaluation outputs |
| Observability | CloudWatch Logs / Metrics / Alarms | Small baseline telemetry footprint |
| Secrets and config | Secrets Manager + SSM Parameter Store | Secrets stay out of the container image |
| Frontend | Amplify Hosting | Optional browser-hosting slice for the checked-in SPA; not required for the backend-shell deploy-now path |

## Baseline cost table

The table below is intentionally directional. It is meant for planning, not for quoting exact AWS prices.

| Component | Baseline AWS service | Primary billing driver | Demo-hours posture | Always-on posture | Cost posture | Why it matters |
| --- | --- | --- | --- | --- | --- | --- |
| API ingress + backend | ALB + ECS Fargate | load balancer hours, task hours, CPU/RAM usage, data transfer | Keep one small task running only during active demo windows when possible | Run continuously for integration windows | **Moderate** | This is the steady backend footprint that makes the API publicly reachable |
| Inference | EC2 GPU instance | GPU instance hours | Start shortly before demo/testing, stop when idle | Runs continuously and becomes the dominant bill | **Highest** | This is the primary cost driver for the capstone baseline |
| Retrieval backend | RDS PostgreSQL + `pgvector` | instance hours, storage, backups | Keep the smallest viable instance; leave on during a demo week or stop only when downtime is acceptable | Runs continuously as the main persistent stateful service | **Moderate to high** | This is the main steady-state cost behind inference |
| Artifact storage | S3 | stored GB-months, requests, lifecycle retention | Low change during demos | Low to moderate growth over time | **Low** | Usually inexpensive, but artifact sprawl should still be controlled |
| Observability | CloudWatch Logs, metrics, alarms | log ingestion, retention, alarms | Short retention and compact logs | Longer retention and more accumulated volume | **Low to moderate** | Can become noisy if raw prompts or verbose payloads are logged |
| Secrets / runtime config | Secrets Manager + SSM Parameter Store | stored secrets, API calls | Nearly fixed | Nearly fixed | **Low** | Operationally important, but not a major spend driver |
| Browser hosting | Amplify Hosting | build/deploy activity, hosting, bandwidth | Deferred | Deferred | **Deferred** | Not part of the backend-shell deploy-now baseline |

## Expected cost shape

For this baseline, the cost profile is simple:

1. **EC2 GPU inference is the main variable spend.** If it stays on, it dominates the bill.
2. **RDS is the main steady infrastructure cost.** Even a small instance is a persistent monthly line item.
3. **ALB + ECS Fargate are the stable application-delivery cost.** They matter, but they should not exceed GPU cost in the default setup.
4. **CloudWatch is usually small until logging becomes too verbose.** Raw prompt/output logging is the easiest way to let observability costs drift upward.
5. **S3 and secrets services should stay comparatively small.** Their cost matters far less than inference, RDS, or idle ALB/Fargate time.

## Biggest cost risks and shutoff levers

| Risk | Why it grows | Shutoff lever |
| --- | --- | --- |
| GPU instance left running when nobody is testing | GPU hours accumulate immediately | Stop the inference instance outside active demo or evaluation windows |
| Oversized RDS choice for a small capstone load | The database runs whether traffic is present or not | Start with the smallest viable PostgreSQL + `pgvector` footprint and resize only if needed |
| ALB + ECS left on continuously without a demo need | The API path keeps billing even when idle | Scale the ECS service down outside scheduled windows if public availability is not needed |
| CloudWatch ingest grows from verbose logs | Large request/response payloads and duplicated logs add up | Log summaries and diagnostic IDs, not full raw prompts or full model outputs by default |
| S3 artifact and snapshot sprawl | Repeated evaluation and ingestion outputs accumulate | Use lifecycle policies and keep only the current plus previous promoted artifact sets |

## Logging and metrics expectations

The baseline ops posture should collect enough information to answer three questions quickly:

1. Is the service up?
2. Is the service healthy enough to demo?
3. Which layer is failing when a query fails?

### Minimum metrics to keep

#### API / ECS / ALB

- ALB healthy target count
- ECS desired vs running task count
- ECS task restarts
- API request count
- API latency (at least p50 and p95 if available from logs or derived metrics)
- HTTP 4xx/5xx rates
- `/healthz` and `/readyz` smoke outcomes during deploy or demo windows

#### Retrieval / database

- RDS availability status
- connection count
- CPU / memory / storage trend
- query failure count or timeout count from application logs
- retrieval latency from application logs

#### Inference

- EC2 instance running state
- CPU / memory usage
- GPU memory / utilization if exposed by the host tooling
- generation latency or timeout count from application logs

#### Trust / product-level signals

- retrieval mode / backend used
- refusal reason code counts
- citation validation failures
- request IDs for cross-layer debugging

### Logging posture

Default to structured JSON logs and keep them compact.

Log by default:

- request ID
- route
- response status
- latency
- retrieval backend / mode
- refusal reason code
- citation-validation outcome

Do **not** log by default:

- raw secrets
- full unredacted prompts
- full model outputs for every request
- large retrieved context payloads

If content capture is needed for debugging, enable it temporarily, redact aggressively, and shorten retention.

## Secrets and runtime configuration

The baseline split is:

### Secrets Manager

Use for values that would be security-sensitive if leaked, including:

- database credentials
- private inference credentials or tokens if introduced later
- any third-party API credentials added after the baseline

### SSM Parameter Store

Use for non-secret runtime configuration, including:

- environment name
- service URLs and internal hostnames
- S3 bucket or prefix names
- retrieval and generation tuning defaults that do not contain secrets

Recommended deploy-now backend-shell values to keep in ECS task environment variables or SSM Parameter Store are:

| Setting | Why it belongs here |
| --- | --- |
| `SUPPORTDOC_DEPLOYMENT_TARGET=aws` | turns on the AWS-targeted runtime validation path |
| `SUPPORTDOC_ENV` | drives the environment label returned by `/readyz` |
| `SUPPORTDOC_API_CORS_ALLOWED_ORIGINS` or `SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX` | defines the explicit browser-origin policy for a separately hosted frontend |
| `SUPPORTDOC_QUERY_RETRIEVAL_MODE=fixture` | keeps the deploy-now backend shell on the supported retrieval path |
| `SUPPORTDOC_QUERY_GENERATION_MODE=fixture` | keeps the first AWS slice self-contained and deterministic |
| `SUPPORTDOC_QUERY_GENERATION_BASE_URL` | non-secret service endpoint only when a compatible HTTP generation backend is introduced |
| `VITE_SUPPORTDOC_API_BASE_URL` | browser-visible API base URL set in Amplify Hosting for the separate SPA |

### IAM and container handling

- ECS tasks should read secrets/config at runtime through IAM permissions, not from committed files
- secrets must not be baked into container images
- local `.env`-style development patterns should not become the cloud deployment source of truth
- the API should fail closed if required secrets/config are missing or malformed
- `/healthz` should stay the ALB target-group health path, while `/readyz` stays the operator-facing compatibility check

## Retention and cleanup guidance

The capstone does not need long-lived production retention defaults. Keep them intentionally short and reviewable.

### CloudWatch

- use short log retention for demo-hours environments
- keep longer retention only during final evaluation windows when evidence is needed for analysis
- delete stale log groups and alarms after the final demo period if the environment will not be reused

### S3

- keep corpus snapshots that are tied to reproducibility claims
- keep only the current promoted artifact set and the immediately previous known-good set for fast rollback
- expire scratch outputs, ad hoc exports, and temporary evaluation files with lifecycle rules where practical

### RDS and database state

- take a snapshot before risky schema or data promotion changes
- delete stale manual snapshots once the final known-good state is preserved elsewhere
- avoid keeping multiple always-on test databases for the same capstone workload

### Compute

- stop the GPU inference instance outside active use
- keep ECS desired count minimal in demo-hours mode
- shut down unused temporary environments after grading or demo windows end

## Day-of-demo runbook

The goal is not full SRE coverage. The goal is a short repeatable checklist that gets the baseline ready and reduces surprise failures.

### Startup checklist

1. Confirm the expected AWS account, region, and environment name.
2. Confirm the promoted artifact set or database snapshot intended for the demo.
3. Start the EC2 GPU inference instance and verify the inference process is healthy.
4. Confirm RDS is available and accepting connections.
5. Set the ECS service to the intended desired count.
6. Wait for the ALB target to report healthy on the `/healthz` target-group path.
7. Call `/healthz`.
8. Call `/readyz` as the operator-facing compatibility check, not as the ALB health path.
9. Run one known-good `/query` smoke request.
10. Check CloudWatch for startup errors before the demo begins.

### Verify checklist

During the active demo window, verify:

- `/healthz` still returns success
- `/readyz` still returns the expected metadata
- one sample query still returns a citation-backed response
- no repeated inference or database failures appear in logs
- ECS task count and ALB target health remain stable

### Shutdown checklist

1. Save any evaluation outputs or demo notes that need to be retained.
2. Scale down the ECS service if public availability is no longer needed.
3. Stop the EC2 GPU inference instance.
4. Leave RDS running only if another near-term session needs it; otherwise stop or snapshot according to the deployment plan.
5. Review CloudWatch log retention and remove any temporary debug-heavy logging settings.

## Quick triage guide

| Symptom | First place to look | Likely cause |
| --- | --- | --- |
| `/healthz` fails | ECS task status, ALB target health, application logs | API container crash, bad deploy, or task boot failure |
| `/healthz` works but `/query` fails | application logs, RDS status, inference host status | retrieval dependency failure or inference backend issue |
| High latency but successful responses | application logs, RDS metrics, inference host metrics | slow retrieval, model latency, or undersized compute |
| Sudden increase in refusals | retrieval diagnostics, database state, artifact promotion history | bad retrieval data, wrong promoted dataset, or dependency drift |
| Log costs spike unexpectedly | CloudWatch log volume and recent debug changes | raw payload logging or overly verbose diagnostics |

## Practical default

For this repo and this capstone, the practical default is:

- keep the **demo-hours posture** as the standard operating mode,
- treat the **EC2 GPU instance** as the main thing to start and stop deliberately,
- keep **RDS small and simple**,
- keep **CloudWatch logs compact**, and
- preserve enough metrics and runbook discipline to prove the deployment is credible.

That is enough operational maturity for the capstone baseline without turning this repo into a full production platform project.
