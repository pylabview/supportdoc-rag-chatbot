#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="supportdoc-rag-chatbot"
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
POSTGRES_MAJOR_VERSION="${POSTGRES_MAJOR_VERSION:-18}"
INSTALL_LOCAL_POSTGRES="${INSTALL_LOCAL_POSTGRES:-auto}"
INSTALL_PGVECTOR_SYSTEM="${INSTALL_PGVECTOR_SYSTEM:-yes}"
INSTALL_NODE_TOOLCHAIN="${INSTALL_NODE_TOOLCHAIN:-yes}"
NODE_VERSION="${NODE_VERSION:-24}"
NVM_VERSION="${NVM_VERSION:-0.40.4}"
PNPM_VERSION="${PNPM_VERSION:-latest-10}"
UV_INSTALL_DIR="${UV_INSTALL_DIR:-$HOME/.local/bin}"

KERNEL_NAME="supportdoc-rag-chatbot-uv-project"
DISPLAY_NAME="Python (${PROJECT_NAME}-uv-project)"

DISTRO_ID=""
DISTRO_VERSION=""
DISTRO_CODENAME=""
DISTRO_LIKE=""
SHELL_PROFILE=""
LOCAL_POSTGRES_ENABLED="false"
POSTGRES_BIN_DIR=""
EXTRAS=()


to_lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

is_truthy() {
  [[ "$(to_lower "${1:-}")" =~ ^(1|y|yes|true)$ ]]
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

detect_shell_profile() {
  local shell_name
  shell_name="$(basename "${SHELL:-}")"

  case "$shell_name" in
    zsh)
      printf '%s/.zshrc' "$HOME"
      ;;
    bash)
      if [[ "$PLATFORM" == "macOS" ]]; then
        printf '%s/.bash_profile' "$HOME"
      else
        printf '%s/.bashrc' "$HOME"
      fi
      ;;
    *)
      if [[ "$PLATFORM" == "macOS" ]]; then
        printf '%s/.zshrc' "$HOME"
      else
        printf '%s/.bashrc' "$HOME"
      fi
      ;;
  esac
}

ensure_profile_file() {
  local file="$1"
  mkdir -p "$(dirname "$file")"
  touch "$file"
}

append_block_if_missing() {
  local file="$1"
  local marker="$2"
  local block="$3"

  ensure_profile_file "$file"

  if grep -Fqs "$marker" "$file"; then
    return 0
  fi

  printf '\n%s\n' "$block" >> "$file"
}

prepend_path_once() {
  local dir="$1"
  case ":$PATH:" in
    *":${dir}:"*) ;;
    *) export PATH="${dir}:$PATH" ;;
  esac
}

ensure_download_tool() {
  if command_exists curl || command_exists wget; then
    return 0
  fi

  if [[ "$PLATFORM" == "Linux" ]]; then
    echo "📦 Installing curl..."
    run_sudo apt-get update
    apt_install curl ca-certificates
    return 0
  fi

  echo "❌ curl or wget is required."
  exit 1
}

ensure_git() {
  if command_exists git; then
    return 0
  fi

  if [[ "$PLATFORM" == "Linux" ]]; then
    echo "📦 Installing git..."
    run_sudo apt-get update
    apt_install git
    return 0
  fi

  if command_exists brew; then
    echo "📦 Installing git via Homebrew..."
    brew install git
    return 0
  fi

  echo "❌ Git (or Xcode Command Line Tools) is required on macOS for nvm."
  echo "Run: xcode-select --install"
  exit 1
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

deb_pkg_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed'
}

load_nvm() {
  export NVM_DIR
  NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"

  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1090
    . "$NVM_DIR/nvm.sh"
  fi
}

ensure_uv() {
  local block

  if command_exists uv; then
    echo "✅ uv already installed: $(uv --version)"
    return 0
  fi

  ensure_download_tool
  mkdir -p "$UV_INSTALL_DIR"

  echo "📦 Installing uv..."
  if command_exists curl; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_INSTALL_DIR" UV_NO_MODIFY_PATH=1 sh
  else
    wget -qO- https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_INSTALL_DIR" UV_NO_MODIFY_PATH=1 sh
  fi

  prepend_path_once "$UV_INSTALL_DIR"

  block=$(cat <<EOF2
# >>> ${PROJECT_NAME}: uv >>>
export PATH="${UV_INSTALL_DIR}:\$PATH"
# <<< ${PROJECT_NAME}: uv <<<
EOF2
)
  append_block_if_missing "$SHELL_PROFILE" "${PROJECT_NAME}: uv" "$block"

  if ! command_exists uv; then
    echo "❌ uv installation completed, but 'uv' is still not on PATH."
    echo "Open a new shell or add ${UV_INSTALL_DIR} to PATH."
    exit 1
  fi

  echo "✅ uv installed: $(uv --version)"
}

ensure_nvm() {
  local block

  load_nvm
  if command_exists nvm; then
    echo "✅ nvm already installed."
    return 0
  fi

  ensure_download_tool
  ensure_git

  if command_exists node; then
    echo "ℹ️ Existing system Node detected ($(node -v 2>/dev/null || true))."
    echo "   Installing nvm as well so this project can pin its own Node version."
  fi

  echo "📦 Installing nvm ${NVM_VERSION}..."
  if command_exists curl; then
    PROFILE=/dev/null bash -c "curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh | bash"
  else
    PROFILE=/dev/null bash -c "wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh | bash"
  fi

  block=$(cat <<'EOF2'
# >>> supportdoc-rag-chatbot: nvm >>>
export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
# <<< supportdoc-rag-chatbot: nvm <<<
EOF2
)
  append_block_if_missing "$SHELL_PROFILE" "supportdoc-rag-chatbot: nvm" "$block"

  load_nvm
  if ! command_exists nvm; then
    echo "❌ nvm installation completed, but 'nvm' could not be loaded in this shell."
    exit 1
  fi

  echo "✅ nvm installed."
}

ensure_node_toolchain() {
  local installed_node=""
  local current_pnpm=""

  case "$(to_lower "${INSTALL_NODE_TOOLCHAIN}")" in
    0|n|no|false)
      echo "⏭️ Skipping Node toolchain installation."
      return 0
      ;;
    auto)
      if ! confirm_default_yes "🟢 Install Node ${NODE_VERSION} + npm + pnpm? (Y/n):" "Y"; then
        echo "⏭️ Skipping Node toolchain installation."
        return 0
      fi
      ;;
  esac

  ensure_nvm
  load_nvm

  installed_node="$(nvm version "${NODE_VERSION}" 2>/dev/null || true)"
  if [[ -n "$installed_node" && "$installed_node" != "N/A" ]]; then
    echo "✅ Node ${installed_node} already installed in nvm."
  else
    echo "📦 Installing Node ${NODE_VERSION} via nvm..."
    nvm install --latest-npm "${NODE_VERSION}"
  fi

  echo "📌 Setting nvm default alias -> ${NODE_VERSION}"
  nvm alias default "${NODE_VERSION}" >/dev/null
  nvm use default >/dev/null

  if ! command_exists node || ! command_exists npm; then
    echo "❌ Node installation failed."
    exit 1
  fi

  echo "✅ node $(node -v)"
  echo "✅ npm  $(npm -v)"

  current_pnpm="$(pnpm --version 2>/dev/null || true)"
  if [[ -n "$current_pnpm" ]]; then
    echo "✅ pnpm ${current_pnpm} already available."
    return 0
  fi

  echo "📦 Installing pnpm (${PNPM_VERSION})..."
  if command_exists corepack; then
    npm install --global corepack@latest
    corepack enable pnpm
    if ! corepack install -g "pnpm@${PNPM_VERSION}"; then
      echo "⚠️ Corepack global pnpm install failed; falling back to npm."
      npm install -g "pnpm@${PNPM_VERSION}"
    fi
  else
    npm install -g "pnpm@${PNPM_VERSION}"
  fi

  if ! command_exists pnpm; then
    echo "❌ pnpm installation failed."
    exit 1
  fi

  echo "✅ pnpm $(pnpm --version)"
}

postgres_major_installed() {
  local version_text=""

  if command_exists psql; then
    version_text="$(psql --version 2>/dev/null || true)"
    if printf '%s' "$version_text" | grep -Eq "PostgreSQL\) ${POSTGRES_MAJOR_VERSION}([. ]|$)"; then
      return 0
    fi
  fi

  if [[ "$PLATFORM" == "macOS" ]]; then
    if command_exists brew && brew list --versions "postgresql@${POSTGRES_MAJOR_VERSION}" >/dev/null 2>&1; then
      return 0
    fi
  else
    if deb_pkg_installed "postgresql-${POSTGRES_MAJOR_VERSION}"; then
      return 0
    fi
  fi

  return 1
}

configure_postgres_path_if_possible() {
  if [[ "$PLATFORM" == "macOS" ]]; then
    if command_exists brew && brew list --versions "postgresql@${POSTGRES_MAJOR_VERSION}" >/dev/null 2>&1; then
      POSTGRES_BIN_DIR="$(brew --prefix "postgresql@${POSTGRES_MAJOR_VERSION}")/bin"
      prepend_path_once "$POSTGRES_BIN_DIR"
    fi
  fi
}

pgvector_extension_present() {
  local sharedir=""

  configure_postgres_path_if_possible
  if ! command_exists pg_config; then
    return 1
  fi

  sharedir="$(pg_config --sharedir 2>/dev/null || true)"
  [[ -n "$sharedir" && -f "${sharedir}/extension/vector.control" ]]
}

install_postgres_macos() {
  local block

  ensure_brew

  if brew list --versions "postgresql@${POSTGRES_MAJOR_VERSION}" >/dev/null 2>&1; then
    echo "✅ PostgreSQL ${POSTGRES_MAJOR_VERSION} already installed via Homebrew."
  else
    echo "🐘 Installing PostgreSQL ${POSTGRES_MAJOR_VERSION} on macOS via Homebrew..."
    brew install "postgresql@${POSTGRES_MAJOR_VERSION}"
  fi

  if is_truthy "${INSTALL_PGVECTOR_SYSTEM}"; then
    if pgvector_extension_present || brew list --versions pgvector >/dev/null 2>&1; then
      echo "✅ pgvector system extension already installed."
    else
      echo "🧠 Installing pgvector system extension..."
      brew install pgvector
    fi
  fi

  brew services start "postgresql@${POSTGRES_MAJOR_VERSION}"
  POSTGRES_BIN_DIR="$(brew --prefix "postgresql@${POSTGRES_MAJOR_VERSION}")/bin"
  prepend_path_once "$POSTGRES_BIN_DIR"

  block=$(cat <<EOF2
# >>> ${PROJECT_NAME}: postgres-${POSTGRES_MAJOR_VERSION} >>>
export PATH="${POSTGRES_BIN_DIR}:\$PATH"
# <<< ${PROJECT_NAME}: postgres-${POSTGRES_MAJOR_VERSION} <<<
EOF2
)
  append_block_if_missing "$SHELL_PROFILE" "${PROJECT_NAME}: postgres-${POSTGRES_MAJOR_VERSION}" "$block"

  echo "✅ PostgreSQL is installed and the service is running."
}

install_postgres_linux() {
  local need_repo="false"

  if [[ -z "${DISTRO_CODENAME:-}" ]]; then
    echo "❌ Could not determine Linux distribution codename from /etc/os-release."
    exit 1
  fi

  if [[ "${DISTRO_ID:-}" != "pop" && "${DISTRO_ID:-}" != "ubuntu" && "${DISTRO_LIKE:-}" != *ubuntu* ]]; then
    echo "❌ PostgreSQL auto-install is currently wired for Pop!_OS / Ubuntu-style systems."
    echo "Detected: ID=${DISTRO_ID:-unknown} VERSION_ID=${DISTRO_VERSION:-unknown}"
    exit 1
  fi

  if ! deb_pkg_installed "postgresql-${POSTGRES_MAJOR_VERSION}"; then
    need_repo="true"
  fi
  if is_truthy "${INSTALL_PGVECTOR_SYSTEM}" && ! deb_pkg_installed "postgresql-${POSTGRES_MAJOR_VERSION}-pgvector"; then
    need_repo="true"
  fi

  if [[ "$need_repo" == "true" ]]; then
    echo "🐘 Installing PostgreSQL ${POSTGRES_MAJOR_VERSION} on ${DISTRO_ID:-Linux} ${DISTRO_VERSION:-}..."
    run_sudo apt-get update
    apt_install curl ca-certificates postgresql-common
    run_sudo install -d /usr/share/postgresql-common/pgdg
    run_sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
      --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
    printf 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
      "${DISTRO_CODENAME}" | run_sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
    run_sudo apt-get update
  else
    echo "✅ PostgreSQL ${POSTGRES_MAJOR_VERSION} already installed."
  fi

  if ! deb_pkg_installed "postgresql-${POSTGRES_MAJOR_VERSION}"; then
    apt_install "postgresql-${POSTGRES_MAJOR_VERSION}" "postgresql-client-${POSTGRES_MAJOR_VERSION}"
  fi

  if is_truthy "${INSTALL_PGVECTOR_SYSTEM}"; then
    if deb_pkg_installed "postgresql-${POSTGRES_MAJOR_VERSION}-pgvector" || pgvector_extension_present; then
      echo "✅ pgvector system extension already installed."
    else
      apt_install "postgresql-${POSTGRES_MAJOR_VERSION}-pgvector"
    fi
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

  if [[ "$should_install" != "true" ]]; then
    echo "⏭️ Skipping local PostgreSQL installation."
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
    if is_truthy "${INSTALL_PGVECTOR_SYSTEM}"; then
      echo "   psql -d supportdoc_rag -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
    fi
  else
    echo "   sudo -u postgres createdb supportdoc_rag"
    if is_truthy "${INSTALL_PGVECTOR_SYSTEM}"; then
      echo "   sudo -u postgres psql -d supportdoc_rag -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
    fi
  fi
}

ensure_venv() {
  if [[ -d ".venv" ]]; then
    if [[ -x ".venv/bin/python" ]]; then
      local venv_ver
      venv_ver="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
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

echo "🔍 Detecting operating system..."
OS="$(uname -s)"
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

SHELL_PROFILE="$(detect_shell_profile)"

echo "✅ Detected: $PLATFORM"
echo "   Shell profile: ${SHELL_PROFILE}"
if [[ "$PLATFORM" == "Linux" ]]; then
  echo "   Linux distro: ${DISTRO_ID:-unknown} ${DISTRO_VERSION:-unknown} (${DISTRO_CODENAME:-no-codename})"
fi

ensure_download_tool
ensure_uv

EXTRAS=("dev-tools")
maybe_install_local_postgres
ensure_node_toolchain

echo "🐍 Ensuring Python ${PYTHON_VERSION} is available..."
uv python install "${PYTHON_VERSION}"

ensure_venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo ""
echo "🧩 Optional Python components:"
echo "1) pgvector Python package only (auto-enabled when local PostgreSQL is installed)"
echo "2) FAISS"
echo "3) Local embeddings"
echo "4) vLLM (Linux + NVIDIA/CUDA)"
echo "5) Evaluation tools"
echo "6) Skip"

OPTIONALS=""
if [[ -t 0 ]]; then
  read -r -p "Select option(s) (comma separated or press Enter to skip): " OPTIONALS || true
else
  echo "ℹ️ Non-interactive shell detected; skipping optional Python components."
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

SYNC_ARGS=()
for extra in "${EXTRAS[@]}"; do
  SYNC_ARGS+=(--extra "$extra")
done

echo ""
echo "📦 Extras to sync: ${EXTRAS[*]}"

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

echo "🔎 Checking Jupyter kernel..."
if uv run python - <<EOF2
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
EOF2
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
echo "📌 Toolchain summary:"
echo "   uv:    $(uv --version)"
echo "   python: $(python --version 2>&1)"
if command_exists node; then
  echo "   node:  $(node -v)"
fi
if command_exists npm; then
  echo "   npm:   $(npm -v)"
fi
if command_exists pnpm; then
  echo "   pnpm:  $(pnpm --version)"
fi
if command_exists psql; then
  echo "   psql:  $(psql --version 2>&1)"
fi

echo ""
echo "🎉 Bootstrap complete!"
echo "Activate with:"
echo "source .venv/bin/activate"
