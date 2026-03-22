# Trust Response Contract

This document records the canonical structured response contract for citation-backed answers and explicit refusals.

## Goal

Define one Pydantic-backed response contract that generation, validation, API serialization, example payloads, and tests can all reuse without ad hoc dictionaries or duplicate dataclasses.

The contract covers three model types:

- `CitationRecord`
- `RefusalRecord`
- `QueryResponse`

## Canonical fields

`QueryResponse` requires:

- `final_answer: str`
- `citations: list[CitationRecord]`
- `refusal: RefusalRecord`

`CitationRecord` requires:

- `marker`
- `doc_id`
- `chunk_id`
- `start_offset`
- `end_offset`

`RefusalRecord` requires:

- `is_refusal`
- `reason_code`
- `message`

Allowed refusal reason codes:

- `insufficient_evidence`
- `no_relevant_docs`
- `citation_validation_failed`
- `out_of_scope`

## Validation rules

The trust contract currently enforces a few cross-field invariants:

- supported answers must include at least one citation
- refusals must return an empty citation list
- refusal payloads must include both a `reason_code` and a user-visible `message`
- non-refusal payloads must set `reason_code` and `message` to `null`
- citation offsets must be non-negative and strictly increasing

## Checked-in review artifacts

The checked-in contract artifacts live under `docs/contracts/`:

- `docs/contracts/query_response.schema.json`
- `docs/contracts/query_response.answer.example.json`
- `docs/contracts/query_response.refusal.example.json`

The JSON Schema is exported from the canonical Pydantic model so reviewers can inspect the API shape directly.

## Exact local commands

Regenerate the checked-in schema artifact:

```bash
uv run python -m supportdoc_rag_chatbot export-trust-schema \
  --output docs/contracts/query_response.schema.json
```

Run the local trust-contract smoke test:

```bash
uv run python -m supportdoc_rag_chatbot smoke-trust-schema \
  --schema docs/contracts/query_response.schema.json \
  --answer-fixture docs/contracts/query_response.answer.example.json \
  --refusal-fixture docs/contracts/query_response.refusal.example.json
```

## Smoke test workflow

The smoke command validates that:

- the checked-in schema still matches the canonical `QueryResponse` model
- the checked-in supported-answer fixture validates successfully
- the checked-in refusal fixture validates successfully

A broader repo verification pass can still use the standard local quality-gate workflow from the README.
