#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_TAG="${SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_IMAGE:-supportdoc-rag-chatbot-api:local}"
CONTAINER_NAME="${SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_NAME:-supportdoc-api-runtime-smoke}"
HOST_PORT="${SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_PORT:-9001}"
TIMEOUT_SECONDS="${SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_TIMEOUT_SECONDS:-90}"
SKIP_BUILD="${SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_SKIP_BUILD:-false}"

usage() {
  cat <<EOF_USAGE
Usage: ./scripts/smoke-container-runtime.sh [options]

Validate the backend container runtime in fixture mode end to end.
The script builds the checked-in backend image by default, starts it with docker run,
waits for the container healthcheck, validates /healthz and /readyz, then checks
supported-answer and refusal responses against the canonical QueryResponse contract.

Options:
  --image-tag TAG          Docker image tag to build/run (default: ${IMAGE_TAG})
  --container-name NAME    Container name to use during the smoke run (default: ${CONTAINER_NAME})
  --host-port PORT         Host port to bind to container port 9001 (default: ${HOST_PORT})
  --timeout-seconds N      Max seconds to wait for container health (default: ${TIMEOUT_SECONDS})
  --skip-build             Reuse an already-built image instead of rebuilding it
  -h, --help               Show this help text

Environment overrides:
  SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_IMAGE
  SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_NAME
  SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_PORT
  SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_TIMEOUT_SECONDS
  SUPPORTDOC_CONTAINER_RUNTIME_SMOKE_SKIP_BUILD=true|false
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

print_diagnostics() {
  echo ""
  echo "Container runtime smoke diagnostics"
  echo "container: ${CONTAINER_NAME}"
  echo "image: ${IMAGE_TAG}"
  echo "host port: ${HOST_PORT}"
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
from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode

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
    with urllib.request.urlopen(request, timeout=10) as response:
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
    raise SystemExit("Supported fixture question returned a refusal response.")
if not supported.citations:
    raise SystemExit("Supported fixture question returned no citations.")
if supported.citations[0].marker != "[1]":
    raise SystemExit(
        f"Supported fixture response returned an unexpected citation marker: {supported.citations[0].marker!r}"
    )

status, refusal_payload = request_json(
    "POST",
    "/query",
    {"question": "How do I reset my laptop BIOS?"},
)
if status != 200:
    raise SystemExit(f"Unexpected refusal /query status: {status}")
refusal = QueryResponse.model_validate(refusal_payload)
if not refusal.refusal.is_refusal:
    raise SystemExit("Refusal fixture question returned a supported answer.")
if refusal.refusal.reason_code is not RefusalReasonCode.NO_RELEVANT_DOCS:
    raise SystemExit(
        "Refusal fixture response returned an unexpected reason code: "
        f"{refusal.refusal.reason_code!r}"
    )
if refusal.citations:
    raise SystemExit("Refusal fixture question returned citations.")

print("Container runtime smoke: ok")
PY
}

require_command docker
require_command uv

cd "${REPO_ROOT}"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
trap cleanup EXIT

if [[ "${SKIP_BUILD}" != "true" ]]; then
  echo "Building backend image ${IMAGE_TAG} from docker/backend.Dockerfile"
  docker build -f docker/backend.Dockerfile -t "${IMAGE_TAG}" . || fail "Backend image build failed."
else
  echo "Skipping image build and reusing ${IMAGE_TAG}"
fi

echo "Starting backend container ${CONTAINER_NAME} on http://127.0.0.1:${HOST_PORT}"
docker run -d --rm \
  --name "${CONTAINER_NAME}" \
  -p "${HOST_PORT}:9001" \
  -e SUPPORTDOC_LOCAL_API_MODE=fixture \
  -e SUPPORTDOC_LOCAL_API_HOST=0.0.0.0 \
  -e SUPPORTDOC_LOCAL_API_PORT=9001 \
  -e SUPPORTDOC_QUERY_GENERATION_MODE=fixture \
  "${IMAGE_TAG}" >/dev/null || fail "Failed to start backend container."

wait_for_container_health || fail "Backend container did not become healthy."
validate_http_contract || fail "Backend container did not satisfy the runtime HTTP contract."

echo "Container runtime smoke completed successfully."
