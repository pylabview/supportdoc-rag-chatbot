# Browser smoke checklist and demo sequence

Use this short checklist before a demo or when you need a reusable browser-proof note for the local web UI.

## Canonical demo path

**Fixture mode is the canonical demo path** for the browser smoke because it uses the checked-in trust fixtures and does not require local retrieval artifacts or a model server.

From the repo root:

```bash
./scripts/run-api-local.sh
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` and keep the backend at `http://127.0.0.1:9001`.

Optional preflight before the manual browser pass:

```bash
bash scripts/smoke-browser-demo.sh
```

## Manual smoke checklist

| Check | How to run it | Expected result | Pass / notes |
| --- | --- | --- | --- |
| Supported answer | Ask `What is a Pod?` and submit. | The page renders **Supported answer**, shows a non-empty `final_answer`, and keeps visible citation markers such as `[1]` inline plus the marker list below the answer. | |
| Refusal | Ask `How do I reset my laptop BIOS?` and submit. | The page renders **Refusal**, shows the refusal text from the backend, shows `reason_code` `no_relevant_docs`, and does not render citation markers for the refusal case. | |
| Empty input | Clear the question box so it contains only whitespace. | Submit stays disabled, no `POST /query` request is sent, and the UI stays in the empty-input treatment instead of showing a result. | |
| Backend unavailable | Stop `./scripts/run-api-local.sh`, then click **Refresh backend status** or submit `What is a Pod?` again. | The page renders the **Backend unavailable** treatment, does not keep stale answer text or stale supported/refusal output on screen, and lets you retry after the backend is back. | |
| Long answer / multi-citation visual check | Keep the browser open, open DevTools Console, and temporarily override `window.fetch` with the sample below. Then submit any non-empty question. | The answer text wraps cleanly, inline markers `[1]`, `[2]`, and `[3]` stay visible, the marker list shows three entries, and the UI still follows the **citation markers only** evidence contract. | |

### Temporary long-answer / multi-citation response override

Use this **visual-only, UI-only** check because the canonical fixture backend returns one short supported answer with a single marker. This one-shot visual override is only for layout proof; it does not change the backend contract.

Paste this into the browser DevTools Console:

```js
window.__supportdocOriginalFetch ??= window.fetch;
window.fetch = async (input, init) => {
  if (String(input).includes('/query')) {
    return new Response(
      JSON.stringify({
        final_answer:
          'Kubernetes Pods can run one or more containers that share networking and storage resources, and the Pod abstraction gives the workload a single execution environment [1]. Higher-level controllers handle replication and rollout behavior, so the browser demo should still render a longer supported answer with multiple visible markers without switching to rich evidence cards [2]. The status area and marker list should remain readable even when the answer grows longer and the layout wraps across lines [3].',
        citations: [
          {
            marker: '[1]',
            doc_id: 'content-en-docs-concepts-workloads-pods-pods',
            chunk_id: 'content-en-docs-concepts-workloads-pods-pods__chunk-0001',
            start_offset: 0,
            end_offset: 180,
          },
          {
            marker: '[2]',
            doc_id: 'content-en-docs-concepts-workloads-pods-pods',
            chunk_id: 'content-en-docs-concepts-workloads-pods-pods__chunk-0002',
            start_offset: 181,
            end_offset: 360,
          },
          {
            marker: '[3]',
            doc_id: 'content-en-docs-concepts-workloads-pods-pods',
            chunk_id: 'content-en-docs-concepts-workloads-pods-pods__chunk-0003',
            start_offset: 361,
            end_offset: 500,
          },
        ],
        refusal: {
          is_refusal: false,
          reason_code: null,
          message: null,
        },
      }),
      {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }
    );
  }
  return window.__supportdocOriginalFetch(input, init);
};
```

When you are done, restore the real backend calls:

```js
if (window.__supportdocOriginalFetch) {
  window.fetch = window.__supportdocOriginalFetch;
  delete window.__supportdocOriginalFetch;
}
```

## Short demo sequence for presentation use

Use this short sequence for a live presentation.

1. Start with the fixture-mode backend and the browser UI already open on `http://127.0.0.1:5173`.
2. Point out that fixture mode is the canonical demo path and that the status area probes `GET /readyz`.
3. Submit `What is a Pod?` to show a supported answer with visible citation markers.
4. Submit `How do I reset my laptop BIOS?` to show an explicit refusal with `reason_code` `no_relevant_docs`.
5. Clear the question box to show that empty input is blocked locally.
6. If you want one resilience check, stop the backend and click **Refresh backend status** to show the backend-unavailable state.
7. If someone asks about long wrapping or multiple markers, use the temporary `window.fetch` override above for a quick visual-only check.

## Simple result-capture template

Copy this table into the final report or live-demo notes.

| Date | Machine | Canonical mode | Supported answer | Refusal | Empty input | Backend unavailable | Long answer / multi-citation | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | macOS arm64 / Pop!_OS x86_64 | fixture mode | pass / fail | pass / fail | pass / fail | pass / fail | pass / fail | |
