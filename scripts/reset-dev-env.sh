#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
  REPO_ROOT="${SCRIPT_DIR}"
elif [[ -f "${SCRIPT_DIR}/../pyproject.toml" ]]; then
  REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
  echo "❌ Could not determine the repo root from: ${SCRIPT_DIR}" >&2
  echo "   Put this script at the repo root or under ./scripts/." >&2
  exit 1
fi

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
KERNEL_NAME="${KERNEL_NAME:-supportdoc-rag-chatbot-uv-project}"

HARD_RESET="false"
REMOVE_LOCK="false"
ALLOW_PYTHON_UNINSTALL="${SUPPORTDOC_RESET_UNINSTALL_UV_PYTHON:-false}"

usage() {
  cat <<EOF_USAGE
Usage:
  ./reset-dev-env.sh [--hard] [--remove-lock]
  ./scripts/reset-dev-env.sh [--hard] [--remove-lock]

Clean local repo state for this checkout only.
Safe to run from any current working directory because cleanup is anchored to the repo root.

Options:
  --remove-lock   Remove repo uv.lock in addition to local caches/build artifacts
  --hard          Stronger cleanup:
                  - implies --remove-lock
                  - clears the uv cache
                  - optionally uninstalls uv-managed Python ${PYTHON_VERSION}
                    only when SUPPORTDOC_RESET_UNINSTALL_UV_PYTHON=true
  -h, --help      Show this help text
EOF_USAGE
}

remove_path() {
  local target="$1"
  local display="$target"

  if [[ "$target" == "$REPO_ROOT" ]]; then
    display="."
  elif [[ "$target" == "$REPO_ROOT/"* ]]; then
    display=".${target#"$REPO_ROOT"}"
  fi

  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf -- "$target"
    echo "🗑️  Removed: $display"
  fi
}

for arg in "$@"; do
  case "$arg" in
    --hard)
      HARD_RESET="true"
      REMOVE_LOCK="true"
      ;;
    --remove-lock)
      REMOVE_LOCK="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown argument: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

echo "🧹 Cleaning local project state under: ${REPO_ROOT}"

# Root-level Python and build artifacts.
for rel_path in \
  ".venv" \
  "venv" \
  ".pytest_cache" \
  ".ruff_cache" \
  ".mypy_cache" \
  ".hypothesis" \
  ".tox" \
  ".nox" \
  ".coverage" \
  "htmlcov" \
  "build" \
  "dist" \
  ".ipynb_checkpoints"
do
  remove_path "${REPO_ROOT}/${rel_path}"
done

# Frontend artifacts used by the local browser demo.
for rel_path in \
  "frontend/node_modules" \
  "frontend/dist" \
  "frontend/.vite" \
  "frontend/.eslintcache"
do
  remove_path "${REPO_ROOT}/${rel_path}"
done

# Coverage leftovers such as .coverage.<suffix>
while IFS= read -r -d '' path; do
  remove_path "$path"
done < <(find "$REPO_ROOT" -maxdepth 1 -type f -name '.coverage.*' -print0 2>/dev/null)

# OS junk files.
while IFS= read -r -d '' path; do
  remove_path "$path"
done < <(find "$REPO_ROOT" -type f -name '.DS_Store' -print0 2>/dev/null)

# Python cache and packaging artifacts anywhere inside the repo.
while IFS= read -r -d '' path; do
  remove_path "$path"
done < <(find "$REPO_ROOT" -type d -name '__pycache__' -prune -print0 2>/dev/null)

while IFS= read -r -d '' path; do
  remove_path "$path"
done < <(find "$REPO_ROOT" -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0 2>/dev/null)

while IFS= read -r -d '' path; do
  remove_path "$path"
done < <(find "$REPO_ROOT" -type d \( -name '*.egg-info' -o -name '.eggs' \) -prune -print0 2>/dev/null)

if [[ "$REMOVE_LOCK" == "true" ]]; then
  remove_path "${REPO_ROOT}/uv.lock"
fi

# Remove the user Jupyter kernel if it exists.
for kernel_dir in \
  "$HOME/Library/Jupyter/kernels/${KERNEL_NAME}" \
  "$HOME/.local/share/jupyter/kernels/${KERNEL_NAME}"
do
  remove_path "$kernel_dir"
done

if [[ "$HARD_RESET" == "true" ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo "🧼 Clearing uv cache..."
    uv cache clean || true

    if [[ "$ALLOW_PYTHON_UNINSTALL" == "true" ]]; then
      echo "🐍 Removing uv-managed Python ${PYTHON_VERSION} because SUPPORTDOC_RESET_UNINSTALL_UV_PYTHON=true"
      uv python uninstall "${PYTHON_VERSION}" || true
    else
      echo "ℹ️  Skipping uv-managed Python uninstall."
      echo "   To enable it, re-run with SUPPORTDOC_RESET_UNINSTALL_UV_PYTHON=true and --hard."
    fi
  else
    echo "ℹ️  uv is not installed, so uv cache/Python cleanup was skipped."
  fi
fi

echo ""
echo "✅ Local cleanup complete."
echo ""
echo "Reinstall dependencies from the repo root:"
echo "  uv sync --locked --extra dev-tools --extra faiss --extra bm25"
if [[ -f "${REPO_ROOT}/frontend/package.json" ]]; then
  echo "  (cd frontend && npm ci)"
fi

echo ""
echo "Start the local demo from the repo root:"
echo "  ./scripts/run-api-local.sh"
if [[ -f "${REPO_ROOT}/frontend/package.json" ]]; then
  echo "  (cd frontend && npm run dev)"
fi
