# SupportDoc RAG Chatbot

SupportDoc is a chatting system that employs an existing Kubernetes documents collection for providing answers to queries. It includes citations where possible for claims it could back up. Where it cannot confirm the validity of its proof, it will simply decline.

## Live MVP

- Frontend: <https://main.dv4rdj3zu8xq.amplifyapp.com>
- Backend API: <https://api.supportdochq.com>
- Repository: <https://github.com/pylabview/supportdoc-rag-chatbot>

Verified browser smoke:

```text
Question: What is a Pod?
Result: Supported answer with citation marker [1]
```

## What this project demonstrates

- Text-based generative AI application.
- Retrieval-augmented generation over Kubernetes documentation.
- Open-source LLM inference with `mistralai/Mistral-7B-Instruct-v0.3` served by vLLM.
- Backend citation validation and structured refusal behavior.
- Deployed React SPA on AWS Amplify.
- Deployed FastAPI backend on ECS/Fargate behind an HTTPS ALB.
- RDS PostgreSQL with `pgvector` for retrieval.
- Private EC2 GPU inference endpoint reachable from ECS only.

## Architecture

```text
Browser
  -> Amplify React SPA
  -> https://api.supportdochq.com/query
  -> ECS/Fargate FastAPI backend
  -> RDS PostgreSQL + pgvector retrieval
  -> Private EC2 vLLM inference endpoint
  -> Citation validation / refusal policy
  -> QueryResponse rendered in the browser
```

Main runtime modes in AWS:

```text
SUPPORTDOC_DEPLOYMENT_TARGET=aws
SUPPORTDOC_QUERY_RETRIEVAL_MODE=pgvector
SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible
SUPPORTDOC_QUERY_GENERATION_BASE_URL=http://10.42.11.221:8000
SUPPORTDOC_QUERY_GENERATION_MODEL=mistralai/Mistral-7B-Instruct-v0.3
```

Frontend build-time setting:

```text
VITE_SUPPORTDOC_API_BASE_URL=https://api.supportdochq.com
```

## API contract

The primary endpoint is:

```text
POST /query
```

Example request:

```json
{
  "question": "What is a Pod?"
}
```

Example successful response shape:

```json
{
  "final_answer": "A Pod is the smallest and simplest Kubernetes object [1].",
  "citations": [
    {
      "marker": "[1]",
      "doc_id": "...",
      "chunk_id": "...",
      "start_offset": 0,
      "end_offset": 144
    }
  ],
  "refusal": {
    "is_refusal": false,
    "reason_code": null,
    "message": null
  }
}
```

Refusals use the same response shape with:

```json
{
  "refusal": {
    "is_refusal": true,
    "reason_code": "insufficient_evidence | no_relevant_docs | citation_validation_failed | out_of_scope",
    "message": "..."
  }
}
```

## Quick smoke checks

Backend health:

```bash
curl -i https://api.supportdochq.com/healthz
curl -i https://api.supportdochq.com/readyz
```

Supported query:

```bash
curl -sS -X POST https://api.supportdochq.com/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is a Pod?"}' \
  | python3 -m json.tool
```

Frontend smoke:

1. Open <https://main.dv4rdj3zu8xq.amplifyapp.com>
2. Ask: `What is a Pod?`
3. Confirm the UI renders a supported answer with citation marker `[1]`.

## Local development

Backend requirements:

- Python `>=3.13,<3.14`
- `uv`

Frontend requirements:

- Node `^20.19.0 || >=22.12.0`
- npm

Install backend dependencies:

```bash
uv sync --locked --extra dev-tools --extra faiss
```

Start local backend in fixture mode:

```bash
./scripts/run-api-local.sh
```

Start local frontend in a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Default local URLs:

```text
Backend: http://127.0.0.1:9001
Frontend: http://127.0.0.1:5173
```

Local frontend override:

```bash
export VITE_SUPPORTDOC_API_BASE_URL=http://127.0.0.1:9001
```

## Repository layout

```text
frontend/                         React/Vite SPA
src/supportdoc_rag_chatbot/app/   FastAPI app and query orchestration
src/supportdoc_rag_chatbot/       Ingestion, retrieval, evaluation, models
data/                             Runtime/evaluation artifacts used locally
docs/contracts/                   QueryResponse schema and examples
docs/ops/                         AWS runbooks, smoke records, operator handoff
infra/aws/                        AWS/Terraform foundation files
scripts/                          Local smoke and helper scripts
tests/                            Unit and integration-style tests
```

## Useful documentation

- `PROPOSAL.md` — capstone proposal and architecture background.
- `docs/ops/task5_cloud_runtime_smoke.md` — cloud runtime smoke record.
- `docs/ops/task5_local_vs_aws_env_matrix.md` — local vs AWS environment matrix.
- `docs/ops/task6_amplify_operator_handoff.md` — final Amplify handoff, rollback, and stop-cost notes.
- `docs/architecture/aws_deployment.md` — AWS deployment architecture notes.
- `docs/contracts/query_response.schema.json` — canonical response contract.

## Stop-cost checklist

After grading/demo, reduce cost in this order:

1. Stop the GPU inference EC2 instance.
2. Scale ECS backend service desired count to `0`.
3. Stop or snapshot/delete RDS according to the grading window.
4. Leave Amplify running only if the public demo URL must remain available.

Resume order:

1. Start RDS and wait until available.
2. Start the inference EC2 instance and verify vLLM.
3. Scale ECS backend service desired count to `1`.
4. Verify `https://api.supportdochq.com/healthz` and `/readyz`.
5. Run the browser smoke again.

## Current MVP scope

This is a capstone MVP that is not a full-blown production offering. It deliberately does not have any multi-tenancy authentication, autoscaling optimization, WAF/rate-limiting, or production-level observability hardening. Its sole purpose is to demonstrate that the end-to-end RAG flow is possible with a working browser application and verified citations.
