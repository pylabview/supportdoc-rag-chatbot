#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
KERNEL_NAME="${KERNEL_NAME:-supportdoc-rag-chatbot-uv-project}"

HARD_RESET="false"
REMOVE_LOCK="false"

usage() {
  cat <<EOF
Usage: ./reset-dev-env.sh [--hard] [--remove-lock]

  --remove-lock   Remove uv.lock in addition to local caches and virtualenvs
  --hard          Do a stronger cleanup:
                  - remove uv.lock
                  - clear uv cache
                  - try to uninstall uv-managed Python ${PYTHON_VERSION}
EOF
}

remove_path() {
  local target="$1"
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf "$target"
    echo "🗑️  Removed: $target"
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
      echo "❌ Unknown argument: $arg"
      usage
      exit 1
      ;;
  esac
done

echo "🧹 Cleaning local project state..."

# Common local env / build artifacts
for path in \
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
  ".ipynb_checkpoints" \
  ".DS_Store"
do
  remove_path "$path"
done

# Egg metadata and Python bytecode
find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
find . -type d \( -name "*.egg-info" -o -name ".eggs" \) -prune -exec rm -rf {} + 2>/dev/null || true

# Optional lock cleanup
if [[ "$REMOVE_LOCK" == "true" ]]; then
  remove_path "uv.lock"
fi

# Remove the user Jupyter kernel if it exists
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

    echo "🐍 Trying to uninstall uv-managed Python ${PYTHON_VERSION}..."
    uv python uninstall "${PYTHON_VERSION}" || true
  else
    echo "ℹ️ uv is not installed, so cache/Python cleanup was skipped."
  fi
fi

echo ""
echo "✅ Local cleanup complete."
echo "Re-run the bootstrap with:"
echo "./bootstrap.sh"
