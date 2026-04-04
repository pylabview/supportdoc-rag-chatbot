#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$repo_root/frontend"
dist_dir="$frontend_dir/dist"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to smoke the browser demo." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to serve the built browser demo." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to fetch the served browser demo." >&2
  exit 1
fi

cd "$frontend_dir"
npm ci
npm run build

server_log="$(mktemp)"
python3 -m http.server 4173 --bind 127.0.0.1 --directory "$dist_dir" >"$server_log" 2>&1 &
server_pid=$!

cleanup() {
  if kill -0 "$server_pid" >/dev/null 2>&1; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -f "$server_log"
}
trap cleanup EXIT

attempt=0
until curl -fsS http://127.0.0.1:4173/ >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then
    echo "Timed out waiting for the browser demo smoke server." >&2
    cat "$server_log" >&2 || true
    exit 1
  fi
  sleep 0.25
done

echo "Browser demo smoke passed."
