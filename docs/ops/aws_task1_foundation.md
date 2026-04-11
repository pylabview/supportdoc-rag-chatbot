# AWS Task 1 foundation decisions and runtime contract

This note is the operator-facing companion to `infra/aws/task1-foundation/`.

It translates the repo's actual backend/frontend config surface into the exact AWS foundation choices needed for **EPIC 12 / Task 1**, plus the Task 1.1 control-plane wiring needed to deploy that stack safely with Terraform remote state and GitHub Actions OIDC.

## Selected MVP defaults

The Task 1 foundation plus Task 1.1 deploy path lock these defaults unless a later task proves they must change:

- **AWS region default:** `us-west-2`
- **environment name:** `mvp`
- **resource naming prefix:** `supportdoc-rag-chatbot-mvp`
- **backend API hostname pattern:** `api.<root_domain_name>`
- **ECR repository:** `supportdoc-rag-chatbot/mvp/backend`
- **S3 bucket pattern:** `supportdoc-rag-chatbot-mvp-<account-id>-us-west-2-artifacts`
- **SSM path prefix:** `/supportdoc-rag-chatbot/mvp`
- **Secrets Manager name prefix:** `supportdoc-rag-chatbot/mvp`
- **backend log group:** `/aws/supportdoc-rag-chatbot/mvp/backend`
- **inference log group:** `/aws/supportdoc-rag-chatbot/mvp/inference`

When the deploy path is wired with the real GitHub repository variables from Task 1.1, those committed defaults resolve to:

- **root domain:** `supportdochq.com`
- **exact hosted zone ID:** `Z04948001WRDOJY1UUZYV`
- **public backend hostname:** `api.supportdochq.com`

## Network layout

The Terraform stack creates one shared VPC with three subnet tiers across two Availability Zones:

- **public subnets** — ALB only
- **private app subnets** — ECS tasks and the private inference host
- **private data subnets** — RDS PostgreSQL

### Route intent

- public subnets route `0.0.0.0/0` to the internet gateway
- private app subnets route `0.0.0.0/0` to a single NAT gateway for the MVP
- private data subnets stay private and do not get a direct internet route

That layout keeps the public HTTPS edge on the ALB, gives ECS and inference an outbound path for image/model downloads, and avoids public database exposure.

## Security groups

Task 1 pins the inbound traffic chain to:

- **ALB SG** — public ingress on `80` and `443`
- **ECS SG** — backend port `9001` from the ALB SG only
- **RDS SG** — PostgreSQL `5432` from the ECS SG only
- **inference SG** — inference port `8000` from the ECS SG only

## Task 1.1 deploy-control plane

Task 1.1 does not change the runtime topology. It adds the safe deployment path around the Task 1 stack:

- Terraform S3 backend with `use_lockfile = true`
- optional exact hosted-zone targeting through `route53_zone_id`
- one GitHub OIDC-trusted IAM role for PR `plan` and `main` `apply`
- one workflow file: `.github/workflows/terraform-task1-foundation.yml`
- one-time AWS bootstrap JSON artifacts kept under `infra/aws/task1-foundation/bootstrap/`

### GitHub repository variables expected by the workflow

Set these repository **Variables** before enabling the workflow:

- `AWS_REGION`
- `AWS_ROLE_ARN`
- `TF_BACKEND_BUCKET`
- `TF_BACKEND_KEY`
- `TF_VAR_PROJECT`
- `TF_VAR_ENVIRONMENT`
- `TF_VAR_ROOT_DOMAIN_NAME`
- `TF_VAR_BACKEND_API_SUBDOMAIN`
- `TF_VAR_ROUTE53_ZONE_ID`

Keep long-lived AWS access keys out of GitHub for this path.

## Repo-aligned runtime contract

The current repo already defines the backend AWS-mode contract and the thin frontend seam.

### Non-secret backend values

Store these in **ECS environment variables** or **SSM Parameter Store** under `/supportdoc-rag-chatbot/mvp/backend/`:

| Env var | Recommended value for the AWS MVP | Notes |
| --- | --- | --- |
| `SUPPORTDOC_DEPLOYMENT_TARGET` | `aws` | Required by the backend when the service runs in AWS mode. |
| `SUPPORTDOC_ENV` | `mvp` | Returned through `/readyz` and used in ops labeling. |
| `SUPPORTDOC_API_CORS_ALLOWED_ORIGINS` | set during Task 4/5 | Must include the real Amplify frontend origin before browser cutover. |
| `SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX` | optional alternative | Use only if the frontend origin cannot be pinned to an exact allowlist. |
| `SUPPORTDOC_QUERY_RETRIEVAL_MODE` | `pgvector` | Final deployed retrieval path required by the EPIC. |
| `SUPPORTDOC_QUERY_PGVECTOR_SCHEMA_NAME` | `supportdoc_rag` | Matches the repo default. |
| `SUPPORTDOC_QUERY_PGVECTOR_RUNTIME_ID` | `default` | Matches the repo default. |
| `SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_MODE` | `local` | Keeps query-time embeddings in-container on ECS. |
| `SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_FIXTURE_PATH` | set only for deterministic smoke tests | Do not use in the normal MVP runtime. |
| `SUPPORTDOC_QUERY_GENERATION_MODE` | `openai_compatible` | Final deployed generation path required by the EPIC. |
| `SUPPORTDOC_QUERY_GENERATION_BASE_URL` | private inference base URL | Non-secret internal service location; set in Task 3/4. Do not include `/v1/chat/completions` in the base URL. |
| `SUPPORTDOC_QUERY_GENERATION_MODEL` | `mistralai/Mistral-7B-Instruct-v0.3` by default | Change only if Task 0 chooses a different inference model identifier. |
| `SUPPORTDOC_QUERY_GENERATION_TIMEOUT_SECONDS` | tune later | Not required for Task 1, but remains a non-secret runtime control. |
| `SUPPORTDOC_QUERY_TOP_K` | tune later | Non-secret retrieval tuning; leave default unless evaluation changes it. |

### Secret backend values

Store these in **AWS Secrets Manager**:

| Env var / secret purpose | Secret name |
| --- | --- |
| RDS master credentials | `supportdoc-rag-chatbot/mvp/database/master-credentials` |
| `SUPPORTDOC_QUERY_PGVECTOR_DSN` | `supportdoc-rag-chatbot/mvp/backend/query-pgvector-dsn` |
| `SUPPORTDOC_QUERY_GENERATION_API_KEY` | `supportdoc-rag-chatbot/mvp/backend/query-generation-api-key` |

The Terraform stack creates those **secret resources as named placeholders** so later tasks can populate values without renaming anything.

### Browser-visible value

Only one public browser config seam should reach Amplify:

| Variable | Where it lives | Purpose |
| --- | --- | --- |
| `VITE_SUPPORTDOC_API_BASE_URL` | Amplify environment variables | Points the React SPA at the public HTTPS backend origin. |

Do not put database credentials, inference keys, retrieval paths, or other backend-only runtime values into the browser environment.

## Task 1 outputs that matter later

Carry these outputs into the later deployment tasks:

- `backend_base_url`
- `backend_target_group_arn`
- `security_group_ids`
- `artifact_bucket_name`
- `ecr_repository_url`
- `ssm_parameter_prefix`
- `secret_names`

## What changed versus the earlier placeholder notes

The repo previously carried AWS guidance as documentation only. Task 1 now adds:

- a real Terraform foundation stack under `infra/aws/task1-foundation/`
- a concrete region default of `us-west-2`
- real reserved names for SSM parameters and Secrets Manager secrets
- a concrete HTTPS ALB + ACM + Route 53 entry point
- a verification script that checks the accepted public/private and exposure boundaries

Task 1.1 layers on top of that with:

- a partial S3 backend block under `infra/aws/task1-foundation/versions.tf`
- exact hosted-zone targeting through `route53_zone_id`
- bootstrap IAM JSON artifacts for the one-time AWS setup
- a GitHub Actions OIDC workflow for PR `plan` and `main` `apply`
