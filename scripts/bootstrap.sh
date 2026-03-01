#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="supportdoc-rag-chatbot"
PYTHON_VERSION="3.13"

KERNEL_NAME="supportdoc-rag-chatbot-uv-project"
DISPLAY_NAME="Python (${PROJECT_NAME}-uv-project)"

echo "🔍 Detecting operating system..."
OS="$(uname -s)"

case "$OS" in
  Darwin) PLATFORM="macOS" ;;
  Linux)  PLATFORM="Linux" ;;
  *)
    echo "❌ Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "✅ Detected: $PLATFORM"

# ----------------------------------------------------
# Ensure uv is installed
# ----------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv is not installed."
  echo "Install from: https://astral.sh/uv/"
  exit 1
fi

# ----------------------------------------------------
# Ensure Python (uv-managed) is available
# ----------------------------------------------------
echo "🐍 Ensuring Python ${PYTHON_VERSION} is available..."
uv python install "${PYTHON_VERSION}"

# ----------------------------------------------------
# Create or reuse virtual environment (ensures correct Python minor)
# ----------------------------------------------------
ensure_venv() {
  if [[ -d ".venv" ]]; then
    if [[ -x ".venv/bin/python" ]]; then
      local venv_ver
      venv_ver="$(".venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      if [[ "$venv_ver" != "$PYTHON_VERSION" ]]; then
        echo "⚠️ Existing .venv uses Python ${venv_ver}, expected ${PYTHON_VERSION}. Recreating..."
        rm -rf .venv
      else
        echo "📦 Reusing existing virtual environment (.venv) [Python ${venv_ver}]"
      fi
    else
      echo "⚠️ Existing .venv looks broken. Recreating..."
      rm -rf .venv
    fi
  fi

  if [[ ! -d ".venv" ]]; then
    echo "📦 Creating virtual environment (.venv)"
    uv venv --python "${PYTHON_VERSION}"
  fi
}

ensure_venv
# shellcheck disable=SC1091
source .venv/bin/activate

# ----------------------------------------------------
# Optional extras selection (collected, then synced once)
# ----------------------------------------------------
EXTRAS=("dev-tools")
OPTIONALS=""

echo ""
echo "🧩 Optional components:"
echo "1) pgvector"
echo "2) FAISS"
echo "3) Local embeddings"
echo "4) vLLM (Linux + NVIDIA/CUDA)"
echo "5) Evaluation tools"
echo "6) Skip"

if [[ -t 0 ]]; then
  read -r -p "Select option(s) (comma separated or press Enter to skip): " OPTIONALS || true
else
  echo "ℹ️ Non-interactive shell detected; skipping optional components."
fi

if [[ -n "${OPTIONALS}" ]]; then
  IFS=',' read -ra CHOICES <<< "${OPTIONALS}"
  for raw in "${CHOICES[@]}"; do
    # trim whitespace so "1, 2" works
    CHOICE="$(echo "$raw" | xargs)"

    case "$CHOICE" in
      1) EXTRAS+=("pgvector") ;;
      2) EXTRAS+=("faiss") ;;
      3) EXTRAS+=("embeddings-local") ;;
      4)
        if [[ "$PLATFORM" != "Linux" ]]; then
          echo "⚠️ vLLM is Linux-only for this project setup. Skipping."
        else
          if command -v nvidia-smi >/dev/null 2>&1 && { [[ -n "${CUDA_HOME:-}" ]] || command -v nvcc >/dev/null 2>&1; }; then
            EXTRAS+=("llm-vllm")
          else
            echo "⚠️ vLLM needs NVIDIA + CUDA toolkit."
            echo "   - Ensure 'nvidia-smi' works"
            echo "   - Install CUDA toolkit (nvcc) or set CUDA_HOME"
            echo "   Skipping vLLM."
          fi
        fi
        ;;
      5) EXTRAS+=("eval") ;;
      6|"") ;; # Skip
      *) echo "⚠️ Unknown option: '$CHOICE' (ignored)" ;;
    esac
  done
fi

# Build uv sync args from selected extras
SYNC_ARGS=()
for extra in "${EXTRAS[@]}"; do
  SYNC_ARGS+=(--extra "$extra")
done

echo ""
echo "📦 Extras to sync: ${EXTRAS[*]}"

# ----------------------------------------------------
# Sync dependencies (lock-aware)
# ----------------------------------------------------
if [[ -f "uv.lock" ]]; then
  echo "📥 Syncing dependencies from lock file..."
  # Try frozen first for reproducibility; if it fails, update lock + env.
  if ! uv sync --frozen "${SYNC_ARGS[@]}"; then
    echo "⚠️ uv.lock doesn't match selected extras / project metadata. Updating lock + environment..."
    uv sync "${SYNC_ARGS[@]}"
  fi
else
  echo "📥 Syncing dependencies..."
  uv sync "${SYNC_ARGS[@]}"
fi

# ----------------------------------------------------
# Linux GPU Optional Torch Upgrade
# ----------------------------------------------------
if [[ "$PLATFORM" == "Linux" ]]; then
  GPU_CHOICE="N"
  if [[ -t 0 ]]; then
    read -r -p "⚡ Install CUDA-enabled PyTorch? (y/N): " GPU_CHOICE || true
  fi

  if [[ "$GPU_CHOICE" =~ ^[Yy]$ ]]; then
    echo "🚀 Installing CUDA PyTorch..."
    uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
  fi
fi

# ----------------------------------------------------
# Jupyter Kernel Setup (Fully Idempotent)
# ----------------------------------------------------
echo "🔎 Checking Jupyter kernel..."

if uv run python - <<EOF
import json, subprocess, sys
try:
    out = subprocess.check_output(
        ["python", "-m", "jupyter", "kernelspec", "list", "--json"]
    )
    data = json.loads(out.decode())
    exists = "${KERNEL_NAME}" in data.get("kernelspecs", {})
    sys.exit(0 if exists else 1)
except Exception:
    sys.exit(1)
EOF
then
  echo "✅ Jupyter kernel already exists."
else
  echo "📓 Installing Jupyter kernel..."
  uv run python -m ipykernel install \
    --user \
    --name "${KERNEL_NAME}" \
    --display-name "${DISPLAY_NAME}"
  echo "✅ Kernel installed."
fi

echo ""
echo "🎉 Bootstrap complete!"
echo "Activate with:"
echo "source .venv/bin/activate"