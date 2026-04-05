#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$repo_root/frontend"
dist_dir="$frontend_dir/dist"

api_host="${SUPPORTDOC_BROWSER_DEMO_SMOKE_API_HOST:-127.0.0.1}"
api_port="${SUPPORTDOC_BROWSER_DEMO_SMOKE_API_PORT:-9001}"
frontend_host="${SUPPORTDOC_BROWSER_DEMO_SMOKE_FRONTEND_HOST:-127.0.0.1}"
frontend_port="${SUPPORTDOC_BROWSER_DEMO_SMOKE_FRONTEND_PORT:-4173}"
timeout_seconds="${SUPPORTDOC_BROWSER_DEMO_SMOKE_TIMEOUT_SECONDS:-90}"

api_log=""
frontend_log=""
api_pid=""
frontend_pid=""

usage() {
  cat <<EOF_USAGE
Usage: bash scripts/smoke-browser-demo.sh

Validate the canonical local browser-demo workflow end to end.
The script starts ./scripts/run-api-local.sh in fixture mode, waits for /readyz,
checks one supported /query response, then builds the checked-in frontend and
serves frontend/dist long enough to confirm the local browser demo stack boots.

Environment overrides:
  SUPPORTDOC_BROWSER_DEMO_SMOKE_API_HOST=127.0.0.1
  SUPPORTDOC_BROWSER_DEMO_SMOKE_API_PORT=9001
  SUPPORTDOC_BROWSER_DEMO_SMOKE_FRONTEND_HOST=127.0.0.1
  SUPPORTDOC_BROWSER_DEMO_SMOKE_FRONTEND_PORT=4173
  SUPPORTDOC_BROWSER_DEMO_SMOKE_TIMEOUT_SECONDS=90

Prerequisites:
  uv sync --locked --extra dev-tools --extra faiss
  Node ^20.19.0 || >=22.12.0
EOF_USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
}

print_diagnostics() {
  echo ""
  echo "Browser demo smoke diagnostics"
  echo "api: http://${api_host}:${api_port}"
  echo "frontend: http://${frontend_host}:${frontend_port}"
  echo "timeout: ${timeout_seconds}"
  if [[ -n "${api_pid}" ]]; then
    echo "api pid: ${api_pid}"
    if kill -0 "${api_pid}" >/dev/null 2>&1; then
      echo "api state: running"
    else
      echo "api state: exited"
    fi
  fi
  if [[ -n "${frontend_pid}" ]]; then
    echo "frontend pid: ${frontend_pid}"
    if kill -0 "${frontend_pid}" >/dev/null 2>&1; then
      echo "frontend state: running"
    else
      echo "frontend state: exited"
    fi
  fi
  if [[ -n "${api_log}" && -f "${api_log}" ]]; then
    echo ""
    echo "API log output"
    cat "${api_log}" || true
  fi
  if [[ -n "${frontend_log}" && -f "${frontend_log}" ]]; then
    echo ""
    echo "Frontend server log output"
    cat "${frontend_log}" || true
  fi
}

cleanup() {
  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" >/dev/null 2>&1; then
    kill "${frontend_pid}" >/dev/null 2>&1 || true
    wait "${frontend_pid}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${api_pid}" ]] && kill -0 "${api_pid}" >/dev/null 2>&1; then
    kill "${api_pid}" >/dev/null 2>&1 || true
    wait "${api_pid}" >/dev/null 2>&1 || true
  fi
  rm -f "${api_log}" "${frontend_log}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
  echo "$*" >&2
  print_diagnostics
  exit 1
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done

  fail "Timed out waiting for ${label}: ${url}"
}

validate_supported_query() {
  API_BASE_URL="http://${api_host}:${api_port}" python3 - <<'PY'
import json
import os
import urllib.request

base_url = os.environ["API_BASE_URL"]
request = urllib.request.Request(
    f"{base_url}/query",
    data=json.dumps({"question": "What is a Pod?"}).encode("utf-8"),
    headers={
        "accept": "application/json",
        "content-type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.load(response)

if payload["refusal"]["is_refusal"]:
    raise SystemExit("Supported browser-demo smoke question returned a refusal response.")
if not payload["final_answer"].strip():
    raise SystemExit("Supported browser-demo smoke question returned an empty final_answer.")
PY
}

validate_frontend_root() {
  FRONTEND_URL="http://${frontend_host}:${frontend_port}/" python3 - <<'PY'
import os
import urllib.request

frontend_url = os.environ["FRONTEND_URL"]
html = urllib.request.urlopen(frontend_url, timeout=5).read().decode("utf-8")
if "SupportDoc Browser Demo" not in html:
    raise SystemExit("Built browser demo root did not contain the expected HTML title.")
PY
}

require_command uv
require_command npm
require_command python3
require_command curl

api_log="$(mktemp)"
frontend_log="$(mktemp)"

cd "$repo_root"
./scripts/run-api-local.sh --mode fixture --host "$api_host" --port "$api_port" >"$api_log" 2>&1 &
api_pid=$!

wait_for_url "http://${api_host}:${api_port}/readyz" "/readyz"
validate_supported_query || fail "Fixture-mode backend query validation failed."

cd "$frontend_dir"
export VITE_SUPPORTDOC_API_BASE_URL="http://${api_host}:${api_port}"
npm ci
npm run build

python3 -m http.server "$frontend_port" --bind "$frontend_host" --directory "$dist_dir" >"$frontend_log" 2>&1 &
frontend_pid=$!

wait_for_url "http://${frontend_host}:${frontend_port}/" "browser demo root"
validate_frontend_root || fail "Frontend root validation failed."

echo "Browser demo smoke passed."
