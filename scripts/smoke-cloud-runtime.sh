#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_TAG="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_IMAGE:-supportdoc-rag-chatbot-api:local}"
CONTAINER_NAME="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_NAME:-supportdoc-api-cloud-runtime-smoke}"
HOST_PORT="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_PORT:-9001}"
TIMEOUT_SECONDS="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_TIMEOUT_SECONDS:-90}"
SKIP_BUILD="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_SKIP_BUILD:-false}"
SKIP_PROMOTION="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_SKIP_PROMOTION:-false}"
DATABASE_URL="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_DATABASE_URL:-}"
GENERATION_BASE_URL="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_GENERATION_BASE_URL:-}"
GENERATION_MODEL="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_GENERATION_MODEL:-}"
GENERATION_API_KEY="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_GENERATION_API_KEY:-}"
SCHEMA_NAME="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_SCHEMA_NAME:-supportdoc_rag}"
RUNTIME_ID="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_RUNTIME_ID:-default}"
CHUNKS_PATH="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_CHUNKS_PATH:-data/processed/chunks.jsonl}"
EMBEDDING_METADATA_PATH="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_EMBEDDING_METADATA_PATH:-data/processed/embeddings/chunk_embeddings.metadata.json}"
EMBEDDER_MODE="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_EMBEDDER_MODE:-local}"
EMBEDDER_FIXTURE_PATH="${SUPPORTDOC_CLOUD_RUNTIME_SMOKE_EMBEDDER_FIXTURE_PATH:-}"

usage() {
  cat <<EOF_USAGE
Usage: ./scripts/smoke-cloud-runtime.sh [options]

Validate the cloud-backed backend runtime path end to end.
The script can optionally promote the current local embedding artifacts into a
pgvector schema, then builds the checked-in backend image, starts it in
pgvector + OpenAI-compatible generation mode, waits for container health,
validates /healthz and /readyz, and checks one supported /query response
against the canonical QueryResponse contract.
Loopback hosts in --database-url and --generation-base-url are preserved for
host-side promotion, then rewritten to host.docker.internal inside Docker.

Required options:
  --database-url URL           PostgreSQL connection string for the pgvector runtime
  --generation-base-url URL    Base URL for the OpenAI-compatible inference endpoint
  --generation-model NAME      Model name sent to the chat completions endpoint

Optional runtime options:
  --schema-name NAME           PostgreSQL schema for the pgvector tables (default: ${SCHEMA_NAME})
  --runtime-id ID              Runtime identifier stored in the metadata table (default: ${RUNTIME_ID})
  --chunks PATH                Path to chunks.jsonl used during promotion (default: ${CHUNKS_PATH})
  --embedding-metadata PATH    Embedding metadata JSON used during promotion (default: ${EMBEDDING_METADATA_PATH})
  --embedder-mode MODE         Query embedder mode inside the backend container (default: ${EMBEDDER_MODE})
  --embedder-fixture-path PATH Fixture embedder path when --embedder-mode fixture is used
  --generation-api-key VALUE   Optional bearer token for the inference endpoint

Optional smoke controls:
  --image-tag TAG              Docker image tag to build/run (default: ${IMAGE_TAG})
  --container-name NAME        Container name to use during the smoke run (default: ${CONTAINER_NAME})
  --host-port PORT             Host port to bind to container port 9001 (default: ${HOST_PORT})
  --timeout-seconds N          Max seconds to wait for container health (default: ${TIMEOUT_SECONDS})
  --skip-build                 Reuse an already-built image instead of rebuilding it
  --skip-promotion             Reuse an already-loaded pgvector runtime instead of reloading artifacts
  -h, --help                   Show this help text

Environment overrides:
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_IMAGE
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_NAME
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_PORT
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_TIMEOUT_SECONDS
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_SKIP_BUILD=true|false
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_SKIP_PROMOTION=true|false
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_DATABASE_URL
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_GENERATION_BASE_URL
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_GENERATION_MODEL
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_GENERATION_API_KEY
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_SCHEMA_NAME
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_RUNTIME_ID
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_CHUNKS_PATH
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_EMBEDDING_METADATA_PATH
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_EMBEDDER_MODE
  SUPPORTDOC_CLOUD_RUNTIME_SMOKE_EMBEDDER_FIXTURE_PATH
EOF_USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --container-name)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --host-port)
      HOST_PORT="$2"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD="true"
      shift
      ;;
    --skip-promotion)
      SKIP_PROMOTION="true"
      shift
      ;;
    --database-url)
      DATABASE_URL="$2"
      shift 2
      ;;
    --generation-base-url)
      GENERATION_BASE_URL="$2"
      shift 2
      ;;
    --generation-model)
      GENERATION_MODEL="$2"
      shift 2
      ;;
    --generation-api-key)
      GENERATION_API_KEY="$2"
      shift 2
      ;;
    --schema-name)
      SCHEMA_NAME="$2"
      shift 2
      ;;
    --runtime-id)
      RUNTIME_ID="$2"
      shift 2
      ;;
    --chunks)
      CHUNKS_PATH="$2"
      shift 2
      ;;
    --embedding-metadata)
      EMBEDDING_METADATA_PATH="$2"
      shift 2
      ;;
    --embedder-mode)
      EMBEDDER_MODE="$2"
      shift 2
      ;;
    --embedder-fixture-path)
      EMBEDDER_FIXTURE_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
}

require_non_blank() {
  local name="$1"
  local value="$2"
  if [[ -z "${value// }" ]]; then
    echo "Missing required option: ${name}" >&2
    exit 1
  fi
}

normalize_container_url() {
  local raw_url="$1"
  NORMALIZE_CONTAINER_URL_INPUT="${raw_url}" uv run python - <<'INNERPY'
from __future__ import annotations

import os
from urllib.parse import SplitResult, urlsplit

raw_url = os.environ["NORMALIZE_CONTAINER_URL_INPUT"]
parts = urlsplit(raw_url)
host = parts.hostname

if host not in {"127.0.0.1", "localhost", "::1"}:
    print(raw_url)
    raise SystemExit(0)

userinfo = ""
if parts.username is not None:
    userinfo = parts.username
    if parts.password is not None:
        userinfo = f"{userinfo}:{parts.password}"
    userinfo = f"{userinfo}@"
port = f":{parts.port}" if parts.port is not None else ""
normalized = SplitResult(
    scheme=parts.scheme,
    netloc=f"{userinfo}host.docker.internal{port}",
    path=parts.path,
    query=parts.query,
    fragment=parts.fragment,
)
print(normalized.geturl())
INNERPY
}

print_diagnostics() {
  echo ""
  echo "Cloud runtime smoke diagnostics"
  echo "container: ${CONTAINER_NAME}"
  echo "image: ${IMAGE_TAG}"
  echo "host port: ${HOST_PORT}"
  echo "schema: ${SCHEMA_NAME}"
  echo "runtime_id: ${RUNTIME_ID}"
  echo ""
  echo "docker ps -a --filter name=${CONTAINER_NAME}"
  docker ps -a --filter "name=^/${CONTAINER_NAME}$" || true
  echo ""
  echo "docker inspect state"
  docker inspect "${CONTAINER_NAME}" --format '{{json .State}}' || true
  echo ""
  echo "docker inspect ports"
  docker inspect "${CONTAINER_NAME}" --format '{{json .NetworkSettings.Ports}}' || true
  echo ""
  echo "docker logs"
  docker logs "${CONTAINER_NAME}" || true
}

fail() {
  echo "$*" >&2
  print_diagnostics
  exit 1
}

wait_for_container_health() {
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  local health_status=""

  while (( SECONDS < deadline )); do
    health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
    case "${health_status}" in
      healthy)
        return 0
        ;;
      unhealthy)
        echo "Container reported unhealthy status." >&2
        return 1
        ;;
    esac
    sleep 2
  done

  echo "Container did not reach healthy status within ${TIMEOUT_SECONDS} seconds." >&2
  return 1
}

validate_http_contract() {
  local base_url="http://127.0.0.1:${HOST_PORT}"
  BASE_URL="${base_url}" uv run python - <<'PY'
import json
import os
import urllib.request

from supportdoc_rag_chatbot.app.api.schemas import HealthStatusResponse, ReadinessStatusResponse
from supportdoc_rag_chatbot.app.schemas import QueryResponse

base_url = os.environ["BASE_URL"].rstrip("/")


def request_json(method: str, path: str, payload: dict[str, str] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, json.load(response)


status, health_payload = request_json("GET", "/healthz")
if status != 200:
    raise SystemExit(f"Unexpected /healthz status: {status}")
HealthStatusResponse.model_validate(health_payload)
if health_payload != {"status": "ok"}:
    raise SystemExit(f"Unexpected /healthz payload: {health_payload!r}")

status, ready_payload = request_json("GET", "/readyz")
if status != 200:
    raise SystemExit(f"Unexpected /readyz status: {status}")
ready = ReadinessStatusResponse.model_validate(ready_payload)
if ready.status != "ready":
    raise SystemExit(f"Unexpected /readyz payload: {ready_payload!r}")

status, supported_payload = request_json(
    "POST",
    "/query",
    {"question": "What is a Pod?"},
)
if status != 200:
    raise SystemExit(f"Unexpected supported /query status: {status}")
supported = QueryResponse.model_validate(supported_payload)
if supported.refusal.is_refusal:
    raise SystemExit("Cloud-backed smoke question returned a refusal response.")
if not supported.citations:
    raise SystemExit("Cloud-backed smoke question returned no citations.")
if supported.citations[0].marker != "[1]":
    raise SystemExit(
        f"Cloud-backed response returned an unexpected citation marker: {supported.citations[0].marker!r}"
    )

print("Cloud runtime smoke: ok")
PY
}

require_command docker
require_command uv

require_non_blank --database-url "${DATABASE_URL}"
require_non_blank --generation-base-url "${GENERATION_BASE_URL}"
require_non_blank --generation-model "${GENERATION_MODEL}"

FIXTURE_MOUNT_ARGS=()

if [[ "${EMBEDDER_MODE}" == "fixture" ]]; then
  require_non_blank --embedder-fixture-path "${EMBEDDER_FIXTURE_PATH}"
fi

cd "${REPO_ROOT}"

CONTAINER_DATABASE_URL="$(normalize_container_url "${DATABASE_URL}")"
CONTAINER_GENERATION_BASE_URL="$(normalize_container_url "${GENERATION_BASE_URL}")"
if [[ "${CONTAINER_DATABASE_URL}" != "${DATABASE_URL}" ]]; then
  echo "Rewriting container pgvector DSN host for Docker runtime: ${DATABASE_URL} -> ${CONTAINER_DATABASE_URL}"
fi
if [[ "${CONTAINER_GENERATION_BASE_URL}" != "${GENERATION_BASE_URL}" ]]; then
  echo "Rewriting container generation base URL host for Docker runtime: ${GENERATION_BASE_URL} -> ${CONTAINER_GENERATION_BASE_URL}"
fi

if [[ "${EMBEDDER_MODE}" == "fixture" ]]; then
  HOST_EMBEDDER_FIXTURE_PATH="$(EMBEDDER_FIXTURE_PATH="${EMBEDDER_FIXTURE_PATH}" uv run python - <<'INNERPY'
from pathlib import Path
import os
print(Path(os.environ["EMBEDDER_FIXTURE_PATH"]).expanduser().resolve())
INNERPY
)"
  if [[ ! -f "${HOST_EMBEDDER_FIXTURE_PATH}" ]]; then
    echo "Fixture embedder file not found: ${HOST_EMBEDDER_FIXTURE_PATH}" >&2
    exit 1
  fi
  CONTAINER_EMBEDDER_FIXTURE_DIR="/app/data/processed/embeddings"
  CONTAINER_EMBEDDER_FIXTURE_PATH="${CONTAINER_EMBEDDER_FIXTURE_DIR}/$(basename "${HOST_EMBEDDER_FIXTURE_PATH}")"
  FIXTURE_MOUNT_ARGS=(
    -v "${HOST_EMBEDDER_FIXTURE_PATH}:${CONTAINER_EMBEDDER_FIXTURE_PATH}:ro"
  )
  EMBEDDER_FIXTURE_PATH="${CONTAINER_EMBEDDER_FIXTURE_PATH}"
fi

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
trap cleanup EXIT

if [[ "${SKIP_PROMOTION}" != "true" ]]; then
  echo "Promoting local embedding artifacts into pgvector schema ${SCHEMA_NAME} (runtime_id=${RUNTIME_ID})"
  uv run python -m supportdoc_rag_chatbot promote-pgvector-runtime \
    --database-url "${DATABASE_URL}" \
    --chunks "${CHUNKS_PATH}" \
    --embedding-metadata "${EMBEDDING_METADATA_PATH}" \
    --schema-name "${SCHEMA_NAME}" \
    --runtime-id "${RUNTIME_ID}" || fail "pgvector runtime promotion failed."
else
  echo "Skipping pgvector runtime promotion and reusing schema ${SCHEMA_NAME}"
fi

if [[ "${SKIP_BUILD}" != "true" ]]; then
  echo "Building backend image ${IMAGE_TAG} from docker/backend.Dockerfile"
  docker build -f docker/backend.Dockerfile -t "${IMAGE_TAG}" . || fail "Backend image build failed."
else
  echo "Skipping image build and reusing ${IMAGE_TAG}"
fi

echo "Starting cloud-backed backend container ${CONTAINER_NAME} on http://127.0.0.1:${HOST_PORT}"
docker run -d --rm \
  --name "${CONTAINER_NAME}" \
  --add-host host.docker.internal:host-gateway \
  "${FIXTURE_MOUNT_ARGS[@]}" \
  -p "${HOST_PORT}:9001" \
  -e SUPPORTDOC_LOCAL_API_MODE=pgvector \
  -e SUPPORTDOC_LOCAL_API_HOST=0.0.0.0 \
  -e SUPPORTDOC_LOCAL_API_PORT=9001 \
  -e SUPPORTDOC_QUERY_RETRIEVAL_MODE=pgvector \
  -e SUPPORTDOC_QUERY_PGVECTOR_DSN="${CONTAINER_DATABASE_URL}" \
  -e SUPPORTDOC_QUERY_PGVECTOR_SCHEMA_NAME="${SCHEMA_NAME}" \
  -e SUPPORTDOC_QUERY_PGVECTOR_RUNTIME_ID="${RUNTIME_ID}" \
  -e SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_MODE="${EMBEDDER_MODE}" \
  -e SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible \
  -e SUPPORTDOC_QUERY_GENERATION_BASE_URL="${CONTAINER_GENERATION_BASE_URL}" \
  -e SUPPORTDOC_QUERY_GENERATION_MODEL="${GENERATION_MODEL}" \
  -e SUPPORTDOC_QUERY_GENERATION_API_KEY="${GENERATION_API_KEY}" \
  -e SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_FIXTURE_PATH="${EMBEDDER_FIXTURE_PATH}" \
  "${IMAGE_TAG}" >/dev/null || fail "Failed to start cloud-backed backend container."

wait_for_container_health || fail "Cloud-backed backend container did not become healthy."
validate_http_contract || fail "Cloud-backed backend container did not satisfy the runtime HTTP contract."

echo "Cloud runtime smoke completed successfully."
