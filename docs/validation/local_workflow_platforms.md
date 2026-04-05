# Local workflow notes for macOS arm64 and Pop!_OS x86_64

This note keeps the **current local browser-demo path** in one place for the two target development machines.

Current repo scope:

- the backend local shell can start in fixture mode with `./scripts/run-api-local.sh`
- the browser UI under `frontend/` remains intentionally thin
- the checked-in browser demo boots locally and points at the expected API base URL
- the checked-in browser demo does send live `POST /query` requests to the local backend

## Runtime baselines

- **Python 3.13** is the required backend baseline. The repo pins it in `.python-version`, and `pyproject.toml` requires `>=3.13,<3.14`.
- **Node `^20.19.0 || >=22.12.0`** is the required frontend baseline for the Vite scaffold.
- `uv` is the canonical Python workflow for both machines.

## Canonical fixture-mode scaffold path

Use the same boring path on both target machines.

1. Sync the backend environment from the repo root:

```bash
uv sync --locked --extra dev-tools --extra faiss
```

2. Start the backend in fixture mode:

```bash
./scripts/run-api-local.sh
```

3. In a second terminal, start the frontend scaffold:

```bash
cd frontend
node -v
npm install
npm run dev
```

Expected local addresses:

- backend fixture shell: `http://127.0.0.1:9001`
- frontend Vite dev server: `http://127.0.0.1:5173`

Optional local checks:

- open `http://127.0.0.1:5173`
- confirm the page renders the scaffold header, question box, result panel, and status area
- confirm the backend reports healthy from `http://127.0.0.1:9001/readyz`

## Target-machine notes

### macOS arm64

- Use the same fixture-mode path above.
- `scripts/bootstrap.sh` can help install Python 3.13 tooling and optional local PostgreSQL support, but PostgreSQL is **not** required for the baseline browser scaffold path.
- `llm-vllm` is **not** part of the macOS path. The package extra is Linux-only in this repo, and the baseline scaffold path does not need it.

### Pop!_OS x86_64

- Use the same fixture-mode path above.
- `scripts/bootstrap.sh` is already wired for Pop!_OS / Ubuntu-style systems when you choose the optional local PostgreSQL install, but PostgreSQL is still **not** required for the baseline browser scaffold path.
- `llm-vllm` remains optional and is **not** required for the baseline browser scaffold path.

## Artifact-mode prerequisites

Artifact mode is the **optional second path** on both machines. Keep it separate from the first-run fixture path.

Before you start the backend with `SUPPORTDOC_LOCAL_API_MODE=artifact`, make sure these local artifacts exist:

- `data/processed/chunks.jsonl`
- `data/processed/indexes/faiss/chunk_index.faiss`
- `data/processed/indexes/faiss/chunk_index.metadata.json`
- `data/processed/indexes/faiss/chunk_index.row_mapping.json`

If your artifacts live somewhere else, set the matching override variables from `src/supportdoc_rag_chatbot/config.py` before launching the backend:

- `SUPPORTDOC_QUERY_ARTIFACT_CHUNKS_PATH`
- `SUPPORTDOC_QUERY_ARTIFACT_INDEX_PATH`
- `SUPPORTDOC_QUERY_ARTIFACT_INDEX_METADATA_PATH`
- `SUPPORTDOC_QUERY_ARTIFACT_ROW_MAPPING_PATH`

Then start artifact mode with:

```bash
SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh
```

Keep the same frontend commands after that:

```bash
cd frontend
node -v
npm install
npm run dev
```

Artifact mode in this repo still defaults to fixture generation unless you explicitly switch generation mode, so it does **not** require a model server just to boot the local scaffold path against local retrieval artifacts.

## Linux-only `llm-vllm` note

`pyproject.toml` restricts the `llm-vllm` extra to `platform_system == 'Linux' and platform_machine == 'x86_64'`. That means:

- **macOS arm64** does not install `llm-vllm`
- **Pop!_OS x86_64** can use it only as an optional Linux path, typically with NVIDIA/CUDA available
- the baseline local browser scaffold path on both target machines does **not** require `llm-vllm`

Treat `llm-vllm` as a later Linux-only inference option, not as a prerequisite for the first local browser-demo run.


For the presentation-ready browser smoke checklist, see `docs/validation/browser_smoke_checklist.md`.
