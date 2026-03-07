#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="supportdoc-rag-chatbot"
PYTHON_VERSION="3.13"
POSTGRES_MAJOR_VERSION="${POSTGRES_MAJOR_VERSION:-18}"
INSTALL_LOCAL_POSTGRES="${INSTALL_LOCAL_POSTGRES:-auto}"
INSTALL_PGVECTOR_SYSTEM="${INSTALL_PGVECTOR_SYSTEM:-yes}"

KERNEL_NAME="supportdoc-rag-chatbot-uv-project"
DISPLAY_NAME="Python (${PROJECT_NAME}-uv-project)"


to_lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

run_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    if ! command_exists sudo; then
      echo "❌ sudo is required for system package installation."
      exit 1
    fi
    sudo "$@"
  fi
}

apt_install() {
  run_sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

confirm_default_yes() {
  local prompt="$1"
  local reply=""
  local default="${2:-Y}"

  if [[ ! -t 0 ]]; then
    [[ "$default" =~ ^[Yy]$ ]]
    return
  fi

  read -r -p "$prompt " reply || true
  reply="${reply:-$default}"
  [[ "$reply" =~ ^[Yy]$ ]]
}

add_extra() {
  local extra="$1"
  local existing
  for existing in "${EXTRAS[@]:-}"; do
    if [[ "$existing" == "$extra" ]]; then
      return 0
    fi
  done
  EXTRAS+=("$extra")
}

ensure_brew() {
  if command_exists brew; then
    return 0
  fi

  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi

  if ! command_exists brew; then
    echo "❌ Homebrew is required on macOS to install PostgreSQL."
    echo "Install it first from: https://brew.sh/"
    exit 1
  fi
}

install_postgres_macos() {
  ensure_brew

  echo "🐘 Installing PostgreSQL ${POSTGRES_MAJOR_VERSION} on macOS via Homebrew..."
  brew install "postgresql@${POSTGRES_MAJOR_VERSION}"

  if [[ "$(to_lower "${INSTALL_PGVECTOR_SYSTEM}")" =~ ^(1|y|yes|true)$ ]]; then
    echo "🧠 Installing pgvector system extension..."
    brew install pgvector
  fi

  brew services start "postgresql@${POSTGRES_MAJOR_VERSION}"

  POSTGRES_BIN_DIR="$(brew --prefix "postgresql@${POSTGRES_MAJOR_VERSION}")/bin"
  export PATH="${POSTGRES_BIN_DIR}:$PATH"

  echo "✅ PostgreSQL is installed and the service is running."
  echo "ℹ️ If 'psql' is not found in future shells, add this to your shell profile:"
  echo "   export PATH=\"${POSTGRES_BIN_DIR}:\$PATH\""
}

install_postgres_linux() {
  if [[ -z "${DISTRO_CODENAME:-}" ]]; then
    echo "❌ Could not determine Linux distribution codename from /etc/os-release."
    exit 1
  fi

  if [[ "${DISTRO_ID:-}" != "pop" && "${DISTRO_ID:-}" != "ubuntu" && "${DISTRO_LIKE:-}" != *ubuntu* ]]; then
    echo "❌ PostgreSQL auto-install is currently wired for Pop!_OS / Ubuntu-style systems."
    echo "Detected: ID=${DISTRO_ID:-unknown} VERSION_ID=${DISTRO_VERSION:-unknown}"
    exit 1
  fi

  echo "🐘 Installing PostgreSQL ${POSTGRES_MAJOR_VERSION} on ${DISTRO_ID:-Linux} ${DISTRO_VERSION:-} ..."
  run_sudo apt-get update
  apt_install curl ca-certificates postgresql-common
  run_sudo install -d /usr/share/postgresql-common/pgdg
  run_sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
  printf 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
    "${DISTRO_CODENAME}" | run_sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null

  run_sudo apt-get update
  apt_install "postgresql-${POSTGRES_MAJOR_VERSION}" "postgresql-client-${POSTGRES_MAJOR_VERSION}"

  if [[ "$(to_lower "${INSTALL_PGVECTOR_SYSTEM}")" =~ ^(1|y|yes|true)$ ]]; then
    apt_install "postgresql-${POSTGRES_MAJOR_VERSION}-pgvector"
  fi

  if command_exists systemctl; then
    run_sudo systemctl enable --now postgresql
  else
    echo "⚠️ systemctl is not available. PostgreSQL was installed, but you may need to start it manually."
  fi

  echo "✅ PostgreSQL is installed."
}

maybe_install_local_postgres() {
  local should_install="false"

  case "$(to_lower "${INSTALL_LOCAL_POSTGRES}")" in
    1|y|yes|true)
      should_install="true"
      ;;
    0|n|no|false)
      should_install="false"
      ;;
    auto|"")
      if confirm_default_yes "🐘 Install local PostgreSQL ${POSTGRES_MAJOR_VERSION} + pgvector system extension? (Y/n):" "Y"; then
        should_install="true"
      fi
      ;;
    *)
      echo "❌ Invalid INSTALL_LOCAL_POSTGRES value: ${INSTALL_LOCAL_POSTGRES}"
      echo "Use: yes | no | auto"
      exit 1
      ;;
  esac

  if [[ "${should_install}" != "true" ]]; then
    return 0
  fi

  if [[ "$PLATFORM" == "macOS" ]]; then
    install_postgres_macos
  else
    install_postgres_linux
  fi

  add_extra "pgvector"
  LOCAL_POSTGRES_ENABLED="true"
}

show_postgres_notes() {
  if [[ "${LOCAL_POSTGRES_ENABLED:-false}" != "true" ]]; then
    return 0
  fi

  echo ""
  echo "📝 PostgreSQL next steps:"
  if command_exists pg_isready; then
    pg_isready || true
  fi

  if [[ "$PLATFORM" == "macOS" ]]; then
    echo "   createdb supportdoc_rag"
    if [[ "$(to_lower "${INSTALL_PGVECTOR_SYSTEM}")" =~ ^(1|y|yes|true)$ ]]; then
      echo "   psql -d supportdoc_rag -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
    fi
  else
    echo "   sudo -u postgres createdb supportdoc_rag"
    if [[ "$(to_lower "${INSTALL_PGVECTOR_SYSTEM}")" =~ ^(1|y|yes|true)$ ]]; then
      echo "   sudo -u postgres psql -d supportdoc_rag -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
    fi
  fi
}

echo "🔍 Detecting operating system..."
OS="$(uname -s)"
DISTRO_ID=""
DISTRO_VERSION=""
DISTRO_CODENAME=""
DISTRO_LIKE=""

case "$OS" in
  Darwin)
    PLATFORM="macOS"
    ;;
  Linux)
    PLATFORM="Linux"
    if [[ -f /etc/os-release ]]; then
      # shellcheck disable=SC1091
      source /etc/os-release
      DISTRO_ID="${ID:-}"
      DISTRO_VERSION="${VERSION_ID:-}"
      DISTRO_CODENAME="${VERSION_CODENAME:-}"
      DISTRO_LIKE="${ID_LIKE:-}"
    fi
    ;;
  *)
    echo "❌ Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "✅ Detected: $PLATFORM"
if [[ "$PLATFORM" == "Linux" ]]; then
  echo "   Linux distro: ${DISTRO_ID:-unknown} ${DISTRO_VERSION:-unknown} (${DISTRO_CODENAME:-no-codename})"
fi

# ----------------------------------------------------
# Ensure uv is installed
# ----------------------------------------------------
if ! command_exists uv; then
  echo "❌ uv is not installed."
  echo "Install from: https://astral.sh/uv/"
  exit 1
fi

# ----------------------------------------------------
# Optional local PostgreSQL install (recommended baseline)
# ----------------------------------------------------
EXTRAS=("dev-tools")
LOCAL_POSTGRES_ENABLED="false"
maybe_install_local_postgres

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
OPTIONALS=""

echo ""
echo "🧩 Optional Python components:"
echo "1) pgvector Python package only (auto-enabled when local PostgreSQL is installed)"
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
    CHOICE="$(echo "$raw" | xargs)"

    case "$CHOICE" in
      1)
        add_extra "pgvector"
        ;;
      2)
        add_extra "faiss"
        ;;
      3)
        add_extra "embeddings-local"
        ;;
      4)
        if [[ "$PLATFORM" != "Linux" ]]; then
          echo "⚠️ vLLM is Linux-only for this project setup. Skipping."
        else
          if command_exists nvidia-smi && { [[ -n "${CUDA_HOME:-}" ]] || command_exists nvcc; }; then
            add_extra "llm-vllm"
          else
            echo "⚠️ vLLM needs NVIDIA + CUDA toolkit."
            echo "   - Ensure 'nvidia-smi' works"
            echo "   - Install CUDA toolkit (nvcc) or set CUDA_HOME"
            echo "   Skipping vLLM."
          fi
        fi
        ;;
      5)
        add_extra "eval"
        ;;
      6|"")
        ;;
      *)
        echo "⚠️ Unknown option: '$CHOICE' (ignored)"
        ;;
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

show_postgres_notes

echo ""
echo "🎉 Bootstrap complete!"
echo "Activate with:"
echo "source .venv/bin/activate"
