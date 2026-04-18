# AWS backend image publish workflow

This document describes the GitHub Actions workflow that builds the backend container image and pushes it to Amazon ECR for the AWS MVP deployment path.

## Why this exists

Task 2 explicitly stops before ECS, inference, or Amplify work, so image publication is not handled there. The AWS execution plan then makes backend image build and push part of Task 4.

## Workflow file

- `.github/workflows/backend-ecr-publish.yml`

## Trigger modes

The workflow supports two paths:

1. `push` to `main` when backend-image inputs change
2. `workflow_dispatch` for manual publishing

## What it publishes

It builds the backend image from:

- `docker/backend.Dockerfile`

and pushes it to the ECR repository derived from existing Terraform repo variables:

- `${{ vars.TF_VAR_PROJECT }}/${{ vars.TF_VAR_ENVIRONMENT }}/backend`

For the current MVP, that should resolve to:

- `supportdoc-rag-chatbot/mvp/backend`

## Required GitHub repo variables

The workflow expects these existing repo variables:

- `AWS_REGION`
- `AWS_ROLE_ARN`
- `TF_VAR_PROJECT`
- `TF_VAR_ENVIRONMENT`

## Required AWS permissions on the GitHub OIDC role

At minimum, the assumed role needs permissions to:

- authenticate to ECR
- describe the target repository
- upload image layers
- push the final image manifest

In practice, make sure the role can perform:

- `ecr:GetAuthorizationToken`
- `ecr:DescribeRepositories`
- `ecr:BatchCheckLayerAvailability`
- `ecr:InitiateLayerUpload`
- `ecr:UploadLayerPart`
- `ecr:CompleteLayerUpload`
- `ecr:PutImage`
- `ecr:BatchGetImage`

## Tagging behavior

- default tag = current commit SHA (12 chars)
- manual dispatch can override with `image_tag`
- `latest` is also pushed on `main` and can be pushed manually

## Recommended ECS usage

Use the SHA-based image URI in ECS task definitions for deterministic deployments.

Example:

```text
675450865367.dkr.ecr.us-west-2.amazonaws.com/supportdoc-rag-chatbot/mvp/backend:<sha-tag>
```

## What this workflow does not do

This workflow only publishes the backend image. It does **not**:

- register an ECS task definition
- create or update the ECS service
- change ALB, target group, or DNS resources
- deploy the frontend

Those remain part of the later AWS execution steps.
