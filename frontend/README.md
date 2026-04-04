# Frontend browser demo scaffold

This directory contains the thin React SPA shell for the local browser demo in Epic 11.

Current scope:

- one page only
- one question input and submit button
- one result panel for answer / refusal / citation placeholders
- one status area for empty input, loading, and backend-unavailable treatment
- no auth, persistence, or multi-page routing
- no live `/query` request yet; that wiring lands in the next scoped task

The UI behavior is pinned to `docs/process/browser_demo_contract.md`.

## Local startup

Use a Node version supported by Vite before installing dependencies. This scaffold targets Node `^20.19.0 || >=22.12.0`.

```bash
cd frontend
node -v
npm install
npm run dev
```

The Vite dev server binds to `http://127.0.0.1:5173` by default.

The checked-in `.npmrc` keeps the lockfile registry-neutral so installs work outside the environment where the lockfile was generated.

If you already hit a failed install once, remove the partial local install and retry:

```bash
cd frontend
rm -rf node_modules
npm install
```

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

## Other useful commands

```bash
cd frontend
npm run build
npm run preview
```
