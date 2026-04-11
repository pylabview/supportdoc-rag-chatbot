# EPIC 12 / Task 1 — AWS foundation + HTTPS entry points

This Terraform stack implements the **Task 1** baseline for the SupportDoc RAG Chatbot MVP using the actual runtime contract present in the repo.

Task 1.1 adds the deploy-control-plane overlay around the same stack:

- a partial S3 backend with native lockfile locking
- exact hosted-zone targeting through an optional `route53_zone_id` input
- bootstrap IAM policy JSONs for the one-time AWS setup you will do manually
- a GitHub Actions workflow for PR `plan` and `main` `apply` via OIDC

## What it creates

- one target region: `us-west-2` by default
- one environment name: `mvp` by default
- one shared naming convention based on `supportdoc-rag-chatbot-mvp`
- one VPC with:
  - **public subnets** for the internet-facing ALB
  - **private app subnets** for ECS tasks and the private inference host
  - **private data subnets** for RDS
- security groups that enforce:
  - public ALB ingress
  - ECS ingress from the ALB only
  - RDS ingress from ECS only
  - inference ingress from ECS only
- one private ECR repository for the backend image
- one versioned S3 artifacts bucket with seeded prefixes:
  - `corpus/`
  - `processed/`
  - `evaluation/outputs/`
  - `deployment/`
- two CloudWatch log groups:
  - backend
  - inference
- one SSM Parameter Store prefix with repo-aligned non-secret runtime defaults
- one Secrets Manager naming scheme with placeholder secret resources for:
  - database master credentials
  - `SUPPORTDOC_QUERY_PGVECTOR_DSN`
  - `SUPPORTDOC_QUERY_GENERATION_API_KEY`
- one public ALB with:
  - HTTP -> HTTPS redirect
  - ACM certificate
  - HTTPS listener
  - Route 53 alias record
  - backend target group pinned to `/healthz`

## Locked defaults

These defaults are baked into this stack to keep the MVP path opinionated and fast:

- **region:** `us-west-2`
- **environment:** `mvp`
- **backend API hostname pattern:** `api.<root_domain_name>`
- **pgvector schema name:** `supportdoc_rag`
- **pgvector runtime id:** `default`
- **generation mode target:** OpenAI-compatible
- **default model identifier:** `mistralai/Mistral-7B-Instruct-v0.3`

With the Task 1.1 GitHub repository variables set to `root_domain_name=supportdochq.com` and `backend_api_subdomain=api`, the deployed hostname becomes `api.supportdochq.com`.

## Prerequisites

- Terraform `>= 1.10`
- AWS credentials with permission to create the listed resources
- an existing **public Route 53 hosted zone**
- a real root domain name you control, for example `example.com`
- a pre-created S3 bucket for Terraform remote state
- a GitHub OIDC-trusted IAM role for the workflow if you want PR `plan` and `main` `apply`

## One-time AWS bootstrap artifacts

The JSON documents you will apply manually in AWS for Task 1.1 live under:

- `infra/aws/task1-foundation/bootstrap/oidc-trust-pr-and-main.json`
- `infra/aws/task1-foundation/bootstrap/supportdoc-tfstate-s3-rw.json`
- `infra/aws/task1-foundation/bootstrap/supportdoc-task1-foundation-apply.json`

## Local deploy flow

```bash
cd infra/aws/task1-foundation
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars so root_domain_name points to a real Route 53 zone you own
# optionally set route53_zone_id to pin the exact hosted zone instead of discovering by name
terraform init \
  -backend-config="bucket=<terraform-state-bucket>" \
  -backend-config="key=supportdoc-rag-chatbot/mvp/task1-foundation.tfstate" \
  -backend-config="region=us-west-2"
terraform plan
terraform apply
```

## GitHub Actions deploy flow

The repo-level workflow is:

- `.github/workflows/terraform-task1-foundation.yml`

Set these GitHub repository **Variables** before enabling the workflow:

- `AWS_REGION`
- `AWS_ROLE_ARN`
- `TF_BACKEND_BUCKET`
- `TF_BACKEND_KEY`
- `TF_VAR_PROJECT`
- `TF_VAR_ENVIRONMENT`
- `TF_VAR_ROOT_DOMAIN_NAME`
- `TF_VAR_BACKEND_API_SUBDOMAIN`
- `TF_VAR_ROUTE53_ZONE_ID`

The workflow uses OIDC only. Do not add long-lived AWS access keys for this path.

## What this stack intentionally does *not* create yet

Task 1 stops at the shared foundation and HTTPS entry points. The following remain for later tasks:

- ECS cluster, service, task definition, and IAM roles
- RDS instance and database creation
- inference EC2 host
- population of actual secret values
- promotion of the runtime dataset into PostgreSQL
- Amplify Hosting

## Outputs you will use later

After `terraform apply`, capture these outputs because later tasks depend on them:

- `backend_base_url`
- `backend_target_group_arn`
- `ecr_repository_url`
- `artifact_bucket_name`
- `security_group_ids`
- `public_subnet_ids`
- `app_private_subnet_ids`
- `data_private_subnet_ids`
- `ssm_parameter_prefix`
- `secret_names`

## Runtime contract

The exact repo-aligned env var and secret split is documented in:

- `docs/ops/aws_task1_foundation.md`

## Verification

Run the companion validation script after apply:

```bash
bash scripts/verify-aws-task1.sh --terraform-dir infra/aws/task1-foundation
```

The script checks:

- ECR repository presence
- S3 write access
- subnet and route-table public/private split
- security-group exposure rules
- HTTPS resolution for the backend API domain
