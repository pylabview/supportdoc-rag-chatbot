# Task 6 — Amplify SPA deployment and operator handoff

## Final deployed URLs

Frontend:
https://main.dv4rdj3zu8xq.amplifyapp.com

Backend API:
https://api.supportdochq.com

## Runtime path proven

Browser → Amplify React SPA → HTTPS backend API → ECS/Fargate → RDS PostgreSQL pgvector → private vLLM inference → citation-validated QueryResponse.

## Browser smoke

Question:

What is a Pod?
### Supported answer

A Pod is the smallest and simplest Kubernetes object [1]. It represents a set of running containers on your cluster [1].

#### Citation markers

This local demo follows the frozen browser contract: citation markers only. Rich evidence cards are deferred because the current `/query`response does not include request-scoped evidence text. Source URL and attribution are not exposed to the browser in the current response shape.

- `[1]`

## Key Amplify settings

App ID:

```
dv4rdj3zu8xq
```

Branch:

```
main
```

Environment variables:

```bash
AMPLIFY_MONOREPO_APP_ROOT=frontend
VITE_SUPPORTDOC_API_BASE_URL=https://api.supportdochq.com
```

## Backend runtime settings

```bash
SUPPORTDOC_DEPLOYMENT_TARGET=aws
SUPPORTDOC_QUERY_RETRIEVAL_MODE=pgvector
SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible
SUPPORTDOC_QUERY_GENERATION_BASE_URL=http://10.42.11.221:8000
SUPPORTDOC_QUERY_GENERATION_MODEL=mistralai/Mistral-7B-Instruct-v0.3
```
