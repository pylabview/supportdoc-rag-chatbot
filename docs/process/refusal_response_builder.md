# Refusal Response Builder

The trust layer now includes a dedicated refusal builder under `src/supportdoc_rag_chatbot/app/services/refusal_builder.py`.

Its job is to turn deterministic upstream failures into a canonical `QueryResponse` refusal payload so downstream API behavior stays stable and machine-readable.

## Canonical reason codes

The refusal builder supports the same canonical reason codes defined by the trust response contract:

- `insufficient_evidence`
- `no_relevant_docs`
- `citation_validation_failed`
- `out_of_scope`

## Canonical messages

The builder renders stable user-facing refusal messages for each reason code:

- `insufficient_evidence` → `I can’t answer that confidently from the approved support corpus.`
- `no_relevant_docs` → `I can’t answer that from the approved support corpus.`
- `citation_validation_failed` → `I can’t provide a supported answer because the citations could not be validated.`
- `out_of_scope` → `I can’t answer that because it is outside the approved support corpus.`

Optional next-step guidance is appended as:

- `Next step: ...`

This keeps the refusal explicit without weakening it.

## Integration points

The same builder can be invoked by:

- retrieval sufficiency gating failures
- citation validation failures
- explicit out-of-scope backend decisions

## Public helpers

- `build_refusal_response(...)`
- `build_refusal_from_retrieval_decision(...)`
- `build_refusal_from_citation_validation(...)`
- `render_refusal_message(...)`

These helpers always return or derive data compatible with the canonical `QueryResponse` schema.
