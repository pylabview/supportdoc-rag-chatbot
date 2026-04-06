# Frontend browser demo scaffold

This directory contains the thin React SPA for the local browser demo in Epic 11.

Current scope:

- one page only
- one question input and submit button
- one result panel for supported answers or refusals from the live backend
- one status area with a tiny `/readyz` indicator for local diagnostics
- visible citation markers in the supported-answer view
- explicit refusal rendering from the structured `refusal` contract, not text heuristics
- marker-only evidence behavior aligned to `docs/process/browser_demo_contract.md`
- a small warning not to paste secrets or sensitive data into the demo
- local empty-input validation and submit-disabled loading behavior
- no auth, persistence, multi-page routing, or rich evidence cards

The UI behavior is pinned to `docs/process/browser_demo_contract.md`.

## Canonical first-run path

Backend prerequisite for the local scaffold path: **Python 3.13** (`.python-version`, `pyproject.toml`). This scaffold also targets Node `^20.19.0 || >=22.12.0`. For macOS arm64 and Pop!_OS x86_64 notes in one place, see `docs/validation/local_workflow_platforms.md`.

Start the local API first from the repo root in **fixture mode**. This is the boring, reliable first-run path because the backend serves deterministic checked-in trust fixtures instead of requiring local retrieval artifacts or a model server.

```bash
./scripts/run-api-local.sh
```

Then start the browser demo in a second terminal:

```bash
cd frontend
node -v
npm install
npm ci
npm run dev
```

Use Node `^20.19.0 || >=22.12.0` for the Vite-based scaffold. The Vite dev server binds to `http://127.0.0.1:5173` by default, while the local API shell binds to `http://127.0.0.1:9001` by default.

The checked-in `.npmrc` keeps the lockfile registry-neutral so installs work outside the environment where the lockfile was generated.

If you already hit a failed install once, remove the partial local install and retry the locked install:

```bash
cd frontend
rm -rf node_modules
npm install
npm ci
```

The FastAPI backend accepts browser requests from the local Vite dev origins by default, so the SPA can call the live API directly during local development.

## Optional second path: artifact mode

Artifact mode is the follow-on path after you already generated local retrieval artifacts. In plain language: fixture mode is for a predictable first demo from checked-in responses, while artifact mode points the browser UI at a backend reading your local `chunks.jsonl` and FAISS files.

Start the backend in artifact mode with:

```bash
SUPPORTDOC_LOCAL_API_MODE=artifact ./scripts/run-api-local.sh
```

Then keep the same frontend commands:

```bash
cd frontend
node -v
npm ci
npm run dev
```

If your artifact files live outside the default `data/processed/` locations, set the documented `SUPPORTDOC_QUERY_ARTIFACT_*` overrides before launching the backend.

## API base URL configuration

The app reads `VITE_SUPPORTDOC_API_BASE_URL` and falls back to `http://127.0.0.1:9001`. That default matches the canonical fixture-mode and artifact-mode backend startup path from `./scripts/run-api-local.sh`.

Override it for local work by copying `.env.example` to `.env.local` and editing the value:

```bash
cd frontend
cp .env.example .env.local
```

```dotenv
VITE_SUPPORTDOC_API_BASE_URL=http://127.0.0.1:9001
```

The value should stay at the browser-visible API origin only, for example `https://api.example.com` without a trailing slash.

For AWS Amplify Hosting, keep using this same variable name as the public browser-side seam:

- set `VITE_SUPPORTDOC_API_BASE_URL` in the Amplify app or branch environment variables
- point it at the public backend origin exposed by the ALB or your API DNS name
- keep secrets, retrieval settings, and backend-only runtime values out of the browser environment

If you host the SPA separately from the backend, the FastAPI service must also allow that frontend origin through `SUPPORTDOC_API_CORS_ALLOWED_ORIGINS` or `SUPPORTDOC_API_CORS_ALLOWED_ORIGIN_REGEX`. Localhost access remains the safe default when those settings are not provided.

## Live browser behavior

- sends `POST /query` with `{ "question": "..." }`
- probes `GET /readyz` for operator-friendly backend status metadata
- renders `final_answer` for both supported answers and refusals
- shows visible citation markers in the answer body and a marker list below it
- uses `refusal.is_refusal` to distinguish supported answers from refusals
- shows `reason_code` as a small refusal diagnostic label
- keeps evidence display to citation markers only
- does not render rich evidence cards or excerpts because the current `/query` response does not expose request-scoped evidence text
- source URL and attribution are not currently available to the browser from the canonical `/query` payload unless the backend exposes `citation.source_url` and `citation.attribution`
- disables submit while a request is in flight
- blocks empty input locally before any network request
- warns users: Do not paste secrets or sensitive data into the demo

## Local browser smoke

From the repo root:

```bash
bash scripts/smoke-browser-demo.sh
```

This combined fixture-mode browser-demo smoke path starts the backend in fixture mode, waits for `GET /readyz`, validates one supported `POST /query` response, builds the SPA from the committed lockfile, and briefly serves `frontend/dist/` so you can confirm the local browser demo stack boots.

For the short manual smoke checklist and presentation sequence, see `docs/validation/browser_smoke_checklist.md`.

## Other useful commands

```bash
cd frontend
npm run build
npm run preview
```
