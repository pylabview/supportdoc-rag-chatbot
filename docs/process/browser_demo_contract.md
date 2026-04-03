# Browser Demo Contract

This document freezes the first browser demo against the currently checked-in backend API so the UI can stay thin and the backend does not grow by accident.

## Scope and reviewed inputs

This contract was reviewed directly against the current ZIP contents:

- `src/supportdoc_rag_chatbot/app/api/routes/query.py`
- `src/supportdoc_rag_chatbot/app/api/routes/system.py`
- `docs/contracts/query_response.schema.json`
- `src/supportdoc_rag_chatbot/app/schemas/trust.py`
- `docs/contracts/query_response.answer.example.json`
- `docs/contracts/query_response.refusal.example.json`
- `docs/contracts/query_response.retrieved_context.example.json`
- `docs/process/trust_response_contract.md`
- `docs/process/citation_validator.md`

The browser demo is pinned to the **current API surface**. It does not introduce streaming, chat-history mutation, extra lookup routes, or client-side document joins.

## Route contract usage

### POST `/query`

`POST /query` is the only required browser request for answer generation.

Request body:

```json
{
  "question": "What is a Pod?"
}
```

Rules:

- the browser trims the input before submit
- the browser does not call `/query` when the trimmed question is empty
- a successful `200` response always uses the canonical `QueryResponse` shape
- the browser branches between supported answer and refusal using `refusal.is_refusal`

### GET `/readyz`

`GET /readyz` is an **optional** browser diagnostic / compatibility probe. The first browser demo does not need to call it before every question.

Current payload fields:

- `status`
- `service`
- `environment`
- `version`
- `query_contract`

Browser rules:

- if the demo chooses to show backend metadata in a footer or debug panel, it should read it from `/readyz`
- if `status != "ready"`, or `query_contract != "QueryResponse"`, the backend should be treated as unavailable or incompatible for the browser demo
- the first browser demo must not invent extra readiness branching beyond that check

### GET `/healthz`

`GET /healthz` is **not** part of the browser demo contract.

It is reserved for infrastructure liveness checks because it only returns `{"status": "ok"}` and does not expose version or response-contract metadata.

## Browser state model

The first browser demo uses exactly these user-visible states.

| State | Entry condition | UI behavior | Exit condition |
| --- | --- | --- | --- |
| `empty_input` | Initial load, or the composer value trims to an empty string | Disable submit. Show no answer panel. Do not call `/query`. | User enters a non-empty question. |
| `loading` | User submits a non-empty question | Disable submit and replace any prior result panel with a single loading treatment. No partial rendering or streaming. | `POST /query` resolves or fails. |
| `supported_answer` | `POST /query` returns `200` and `refusal.is_refusal == false` | Render `final_answer` as the primary answer text. Keep the parsed `citations` in state, but do not render evidence cards in the first iteration. | User edits input or submits another question. |
| `refusal` | `POST /query` returns `200` and `refusal.is_refusal == true` | Render `final_answer` as the primary refusal text. The UI may optionally show `refusal.reason_code` as a small diagnostic label, but it does not branch to different layouts per reason code. | User edits input or submits another question. |
| `backend_unavailable` | Network failure, timeout, or any non-`200` response from `/query`; optional `/readyz` failure if the browser probes readiness | Show one generic backend-unavailable treatment with retry affordance. Do not attempt partial answer rendering. The thin client may surface backend `error.message` when present, but it does not create extra error-specific states. | Retry succeeds, or the user returns to editing input. |

Notes:

- backend `422` validation errors are not part of the normal browser flow because blank input is blocked locally
- the browser state machine is intentionally single-turn and request/response only

## `QueryResponse` to UI mapping

The browser must interpret the response fields like this.

| Field | Browser behavior | Notes |
| --- | --- | --- |
| `final_answer` | Always render this as the main visible text for a `200` response. | This applies to both supported answers and refusals. The UI does not concatenate `final_answer` with any other text. |
| `citations` | Preserve in state with the current result. | For supported answers this list is non-empty by contract. For refusals it is empty by contract. The first browser demo does not use this list to build evidence cards. |
| `refusal.is_refusal` | Use this as the single branch that selects `supported_answer` vs `refusal`. | Do not infer refusal from citation count or string matching. |
| `refusal.reason_code` | Optional diagnostic or analytics field only. | The first browser demo does not create separate user-facing flows for `insufficient_evidence`, `no_relevant_docs`, `citation_validation_failed`, or `out_of_scope`. |
| `refusal.message` | Treat as duplicate refusal metadata rather than a second visible body. | The trust contract requires it for refusals, but the first browser demo renders `final_answer` only. |

If the browser performs the optional readiness probe, it should interpret `/readyz` like this.

| Field | Browser behavior | Notes |
| --- | --- | --- |
| `status` | Treat `"ready"` as compatible. Anything else is unavailable/incompatible. | Current route is deterministic. |
| `service`, `environment`, `version` | Optional footer or debug metadata only. | No UI branching depends on these values. |
| `query_contract` | Expect `"QueryResponse"`. | This is the only readiness field that directly pins the browser to the current response contract. |

## Evidence rendering decision

The first browser demo renders **citation markers only**.

That means:

- the browser renders `final_answer` exactly as returned, including inline markers such as `[1]`
- the browser does **not** attempt to dereference `doc_id`, `chunk_id`, or offsets on the client
- the browser does **not** render expandable evidence cards, modals, or drawers in this first iteration
- the browser does **not** make the markers clickable in this first iteration

This is the smallest viable contract because the current `QueryResponse` only exposes citation pointers. It does **not** return the evidence text and source payload needed for a clean rich-card UI.

The checked-in `docs/contracts/query_response.retrieved_context.example.json` fixture is a validator input, not a browser response contract. The browser must not treat that fixture as if `/query` returned it.

## Tightly scoped follow-up if rich evidence cards become mandatory

If a later browser iteration must show clickable evidence cards, the smallest backend addition should be a **request-scoped evidence payload added to `QueryResponse`** rather than a separate client-side lookup flow.

That follow-up should stay narrow:

- keep `POST /query` as the only required browser request
- add backend-generated evidence records keyed by the already returned citation markers
- include only the fields needed to render a card cleanly, for example marker, source identity, and evidence text/excerpt
- derive the payload from the already validated retrieved context for that request
- avoid making the frontend reconstruct evidence cards from raw `doc_id` / `chunk_id` pointers

That follow-up is **not** part of this task.

## Non-goals for this task

This contract freeze does not add:

- streaming or server-sent events
- multi-turn chat history
- per-reason refusal UX variants
- extra browser-only backend routes
- client-side citation resolution against stored corpus artifacts
