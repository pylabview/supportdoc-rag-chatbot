# Frontend browser demo

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

## Local startup

Start the local API first from the repo root:

```bash
./scripts/run-api-local.sh
```

Then start the browser demo:

```bash
cd frontend
node -v
npm install
npm run dev
```

Use Node `^20.19.0 || >=22.12.0` for the Vite-based scaffold. The Vite dev server binds to `http://127.0.0.1:5173` by default.

The checked-in `.npmrc` keeps the lockfile registry-neutral so installs work outside the environment where the lockfile was generated.

If you already hit a failed install once, remove the partial local install and retry:

```bash
cd frontend
rm -rf node_modules
npm install
```

The FastAPI backend accepts browser requests from the local Vite dev origins, so the SPA can call the live API directly during local development.

## API base URL configuration

The app reads `VITE_SUPPORTDOC_API_BASE_URL` and falls back to `http://127.0.0.1:9001`.

Override it for local work by copying `.env.example` to `.env.local` and editing the value:

```bash
cd frontend
cp .env.example .env.local
```

```dotenv
VITE_SUPPORTDOC_API_BASE_URL=http://127.0.0.1:9001
```

## Live browser behavior

- sends `POST /query` with `{ "question": "..." }`
- renders `final_answer` for both supported answers and refusals
- shows visible citation markers in the answer body and a marker list below it
- uses `refusal.is_refusal` to distinguish supported answers from refusals
- shows `reason_code` as a small refusal diagnostic label
- keeps evidence display to citation markers only
- does not render rich evidence cards or excerpts because the current `/query` response does not expose request-scoped evidence text
- source URL and attribution are not currently available to the browser from the canonical `/query` payload
- disables submit while a request is in flight
- blocks empty input locally before any network request
- warns users: Do not paste secrets or sensitive data into the demo
- probes `GET /readyz` for operator-friendly backend status metadata

## Local browser smoke

From the repo root:

```bash
bash scripts/smoke-browser-demo.sh
```

This smoke path installs from the committed lockfile, builds the SPA, and briefly serves `frontend/dist/` so you can confirm the local browser demo boots.

## Other useful commands

```bash
cd frontend
npm run build
npm run preview
```
