# Task 5 local-vs-AWS environment variable matrix

| Variable | Local/dev value | AWS/ECS MVP value | Notes |
|---|---|---|---|
| `SUPPORTDOC_DEPLOYMENT_TARGET` | local/dev | `aws` | ECS task runs in AWS mode. |
| `SUPPORTDOC_ENV` | local/dev | `mvp` | MVP environment label. |
| `SUPPORTDOC_LOCAL_API_MODE` | `fixture` or local mode | `pgvector` | ECS backend uses real pgvector retrieval. |
| `SUPPORTDOC_LOCAL_API_HOST` | `127.0.0.1` or `0.0.0.0` | `0.0.0.0` | Container must listen on all interfaces. |
| `SUPPORTDOC_LOCAL_API_PORT` | `9001` | `9001` | ALB target group forwards to container port 9001. |
| `SUPPORTDOC_QUERY_RETRIEVAL_MODE` | `fixture` or local | `pgvector` | Required for cloud RDS retrieval. |
| `SUPPORTDOC_QUERY_PGVECTOR_DSN` | local DSN or unset | ECS secret from Secrets Manager | Injected from `supportdoc-rag-chatbot/mvp/backend/query-pgvector-dsn`. Do not log full value. |
| `SUPPORTDOC_QUERY_PGVECTOR_SCHEMA_NAME` | `supportdoc_rag` | `supportdoc_rag` | Runtime schema. |
| `SUPPORTDOC_QUERY_PGVECTOR_RUNTIME_ID` | `default` | `default` | Runtime ID loaded in Task 2. |
| `SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_MODE` | `local` | `local` | Backend embeds query locally. |
| `SUPPORTDOC_QUERY_GENERATION_MODE` | `fixture` or local | `openai_compatible` | ECS calls private vLLM endpoint. |
| `SUPPORTDOC_QUERY_GENERATION_BASE_URL` | local test URL | `http://10.42.11.221:8000` | Base URL must not include `/v1`. |
| `SUPPORTDOC_QUERY_GENERATION_MODEL` | test model or fixture | `mistralai/Mistral-7B-Instruct-v0.3` | Must match vLLM-served model. |
| `SUPPORTDOC_QUERY_GENERATION_TIMEOUT_SECONDS` | default/local | `120` | Allows slow GPU responses. |
| `SUPPORTDOC_QUERY_TOP_K` | default/local | `3` | MVP retrieval top-k used in ECS. |
| `SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX` | local frontend origin | currently permissive for MVP | Tighten to Amplify origin after Task 6. |
| `VITE_SUPPORTDOC_API_BASE_URL` | local API URL | real HTTPS backend origin | Used by React/Amplify; must be browser-valid HTTPS. |
