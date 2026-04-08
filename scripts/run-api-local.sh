#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="${SUPPORTDOC_LOCAL_API_MODE:-fixture}"
HOST="${SUPPORTDOC_LOCAL_API_HOST:-127.0.0.1}"
PORT="${SUPPORTDOC_LOCAL_API_PORT:-9001}"
RELOAD="${SUPPORTDOC_LOCAL_API_RELOAD:-false}"
GENERATION_MODE="${SUPPORTDOC_QUERY_GENERATION_MODE:-fixture}"

usage() {
  cat <<EOF
Usage: ./scripts/run-api-local.sh [--mode fixture|artifact|pgvector] [--host 127.0.0.1] [--port 9001] [--reload]

Defaults:
  mode   fixture
  host   127.0.0.1
  port   9001

Examples:
  ./scripts/run-api-local.sh
  ./scripts/run-api-local.sh --mode artifact
  SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh
  SUPPORTDOC_LOCAL_API_MODE=pgvector SUPPORTDOC_QUERY_PGVECTOR_DSN=postgresql://... \
    SUPPORTDOC_QUERY_GENERATION_MODE=openai_compatible SUPPORTDOC_QUERY_GENERATION_BASE_URL=http://127.0.0.1:8080 \
    SUPPORTDOC_QUERY_GENERATION_MODEL=demo-model ./scripts/run-api-local.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --reload)
      RELOAD="true"
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

cd "$REPO_ROOT"

export SUPPORTDOC_QUERY_RETRIEVAL_MODE="$MODE"
export SUPPORTDOC_QUERY_GENERATION_MODE="$GENERATION_MODE"

uv run python - <<'PY'
import sys

from supportdoc_rag_chatbot.app.core import (
    LocalWorkflowError,
    ensure_local_api_ready,
    evaluate_local_api_readiness,
    render_local_api_preflight_report,
)
from supportdoc_rag_chatbot.config import get_backend_settings

settings = get_backend_settings()
report = evaluate_local_api_readiness(settings)
print(render_local_api_preflight_report(report), flush=True)
try:
    ensure_local_api_ready(settings)
except LocalWorkflowError as exc:
    print("", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    raise SystemExit(1) from exc
PY

uvicorn_args=(
  supportdoc_rag_chatbot.app.api:app
  --host "$HOST"
  --port "$PORT"
)

if [[ "$RELOAD" == "true" ]]; then
  uvicorn_args+=(--reload)
fi

echo ""
echo "Starting local API on http://${HOST}:${PORT} (mode=${MODE}, generation=${GENERATION_MODE})"
exec uv run uvicorn "${uvicorn_args[@]}"
