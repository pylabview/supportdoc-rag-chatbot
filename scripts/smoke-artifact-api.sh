#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HOST="${SUPPORTDOC_ARTIFACT_API_SMOKE_HOST:-127.0.0.1}"
PORT="${SUPPORTDOC_ARTIFACT_API_SMOKE_PORT:-9002}"
TIMEOUT_SECONDS="${SUPPORTDOC_ARTIFACT_API_SMOKE_TIMEOUT_SECONDS:-90}"
KEEP_TEMP="${SUPPORTDOC_ARTIFACT_API_SMOKE_KEEP_TEMP:-false}"

TEMP_DIR=""
LOG_PATH=""
SERVER_PID=""

usage() {
  cat <<EOF_USAGE
Usage: ./scripts/smoke-artifact-api.sh [options]

Validate the artifact-backed local API path end to end using a deterministic smoke fixture.
The script materializes a tiny chunks + FAISS fixture in a temporary directory, starts the
backend in artifact mode with explicit artifact-path overrides, waits for /readyz, then
validates supported-answer and refusal responses against the canonical QueryResponse contract.

Options:
  --host HOST             Bind host for the local API server (default: ${HOST})
  --port PORT             Bind port for the local API server (default: ${PORT})
  --timeout-seconds N     Max seconds to wait for API readiness (default: ${TIMEOUT_SECONDS})
  --keep-temp             Keep the generated temporary fixture directory after the run
  -h, --help              Show this help text

Environment overrides:
  SUPPORTDOC_ARTIFACT_API_SMOKE_HOST
  SUPPORTDOC_ARTIFACT_API_SMOKE_PORT
  SUPPORTDOC_ARTIFACT_API_SMOKE_TIMEOUT_SECONDS
  SUPPORTDOC_ARTIFACT_API_SMOKE_KEEP_TEMP=true|false

Prerequisite:
  uv sync --locked --extra dev-tools --extra faiss
EOF_USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --keep-temp)
      KEEP_TEMP="true"
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

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
}

cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_TEMP}" != "true" ]] && [[ -n "${TEMP_DIR}" ]] && [[ -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}" >/dev/null 2>&1 || true
  fi
}

print_diagnostics() {
  echo ""
  echo "Artifact-mode API smoke diagnostics"
  echo "host: ${HOST}"
  echo "port: ${PORT}"
  echo "timeout: ${TIMEOUT_SECONDS}"
  if [[ -n "${TEMP_DIR}" ]]; then
    echo "fixture dir: ${TEMP_DIR}"
    if [[ -d "${TEMP_DIR}" ]]; then
      echo "generated files:"
      find "${TEMP_DIR}" -maxdepth 2 -type f | sort || true
    fi
  fi
  if [[ -n "${SERVER_PID}" ]]; then
    echo "server pid: ${SERVER_PID}"
    if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
      echo "server state: running"
    else
      echo "server state: exited"
    fi
  fi
  if [[ -n "${LOG_PATH}" ]] && [[ -f "${LOG_PATH}" ]]; then
    echo ""
    echo "API log output"
    cat "${LOG_PATH}" || true
  fi
}

fail() {
  echo "$*" >&2
  print_diagnostics
  exit 1
}

build_fixture() {
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/supportdoc-artifact-api-smoke.XXXXXX")"
  LOG_PATH="${TEMP_DIR}/artifact-api-smoke.log"
  ARTIFACT_SMOKE_OUTPUT_DIR="${TEMP_DIR}" uv run python - <<'PY'
import os
from pathlib import Path

from supportdoc_rag_chatbot.app.core.artifact_smoke import (
    build_artifact_smoke_fixture,
    render_artifact_smoke_fixture_report,
)

output_dir = Path(os.environ["ARTIFACT_SMOKE_OUTPUT_DIR"])
fixture = build_artifact_smoke_fixture(output_dir)
print(render_artifact_smoke_fixture_report(fixture))
PY
}

wait_for_api_ready() {
  local base_url="http://${HOST}:${PORT}"
  BASE_URL="${base_url}" TIMEOUT_SECONDS="${TIMEOUT_SECONDS}" uv run python - <<'PY'
import json
import os
import time
import urllib.error
import urllib.request

base_url = os.environ["BASE_URL"].rstrip("/")
deadline = time.monotonic() + float(os.environ["TIMEOUT_SECONDS"])
last_error = "artifact-mode API never became ready"

while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(f"{base_url}/readyz", timeout=2) as response:
            payload = json.load(response)
        if response.status == 200 and payload.get("status") == "ready":
            raise SystemExit(0)
        last_error = f"Unexpected /readyz payload: {payload!r}"
    except urllib.error.URLError as exc:
        last_error = str(exc)
    except TimeoutError as exc:  # pragma: no cover - platform-specific network timing
        last_error = str(exc)
    time.sleep(1)

raise SystemExit(last_error)
PY
}

validate_http_contract() {
  local base_url="http://${HOST}:${PORT}"
  BASE_URL="${base_url}" FIXTURE_DIR="${TEMP_DIR}" uv run python - <<'PY'
import json
import os
import urllib.request
from pathlib import Path

from supportdoc_rag_chatbot.app.api.schemas import HealthStatusResponse, ReadinessStatusResponse
from supportdoc_rag_chatbot.app.schemas import QueryResponse, RefusalReasonCode

base_url = os.environ["BASE_URL"].rstrip("/")
fixture_dir = Path(os.environ["FIXTURE_DIR"])
chunks_path = fixture_dir / "chunks.jsonl"
with chunks_path.open("r", encoding="utf-8") as handle:
    chunk_ids = {json.loads(line)["chunk_id"] for line in handle if line.strip()}


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
    raise SystemExit("Supported artifact smoke question returned a refusal response.")
if not supported.citations:
    raise SystemExit("Supported artifact smoke question returned no citations.")
returned_chunk_ids = {citation.chunk_id for citation in supported.citations}
if not returned_chunk_ids.issubset(chunk_ids):
    raise SystemExit(
        "Supported artifact smoke response cited chunk IDs outside the loaded fixture: "
        f"{sorted(returned_chunk_ids - chunk_ids)!r}"
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
    raise SystemExit("Refusal artifact smoke question returned a supported answer.")
if refusal.refusal.reason_code is not RefusalReasonCode.NO_RELEVANT_DOCS:
    raise SystemExit(
        "Refusal artifact smoke response returned an unexpected reason code: "
        f"{refusal.refusal.reason_code!r}"
    )
if refusal.citations:
    raise SystemExit("Refusal artifact smoke question returned citations.")

print("Artifact-mode API smoke: ok")
PY
}

start_api_server() {
  (
    export SUPPORTDOC_LOCAL_API_MODE=artifact
    export SUPPORTDOC_LOCAL_API_HOST="${HOST}"
    export SUPPORTDOC_LOCAL_API_PORT="${PORT}"
    export SUPPORTDOC_QUERY_GENERATION_MODE=fixture
    export SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH="${TEMP_DIR}/chunks.jsonl"
    export SUPPORTDOC_QUERY_ARTIFACT_INDEX_PATH="${TEMP_DIR}/chunk_index.faiss"
    export SUPPORTDOC_QUERY_ARTIFACT_INDEX_METADATA_PATH="${TEMP_DIR}/chunk_index.metadata.json"
    export SUPPORTDOC_QUERY_ARTIFACT_ROW_MAPPING_PATH="${TEMP_DIR}/chunk_index.row_mapping.json"
    export SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_MODE=fixture
    export SUPPORTDOC_QUERY_ARTIFACT_EMBEDDER_FIXTURE_PATH="${TEMP_DIR}/query_embedding_fixture.json"
    ./scripts/run-api-local.sh --mode artifact --host "${HOST}" --port "${PORT}"
  ) >"${LOG_PATH}" 2>&1 &
  SERVER_PID="$!"
}

require_command uv

cd "${REPO_ROOT}"
trap cleanup EXIT

build_fixture || fail "Artifact smoke fixture build failed."
start_api_server || fail "Artifact-mode API server failed to start."
wait_for_api_ready || fail "Artifact-mode API did not become ready."
validate_http_contract || fail "Artifact-mode API did not satisfy the HTTP smoke contract."

echo "Artifact-mode API smoke completed successfully."
