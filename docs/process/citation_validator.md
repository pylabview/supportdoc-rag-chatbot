# Citation Validator

This document records the deterministic backend validator for citation-backed answers.

## Goal

Given a structured `QueryResponse` plus the request-scoped retrieved chunk metadata, determine whether the generated answer is safe to accept as-is, should be regenerated, or should be converted into a refusal.

The validator is intentionally pure and side-effect free so later backend orchestration can reuse it directly.

## Module entry points

- `src/supportdoc_rag_chatbot/app/services/citation_validator.py`
- `src/supportdoc_rag_chatbot/app/services/sentence_splitter.py`

## Deterministic checks

Supported answers are validated against these rules:

- every sentence or bullet item must contain at least one citation marker
- every marker in `final_answer` must resolve to one `CitationRecord`
- citation markers must use bracketed numeric form such as `[1]`
- cited `chunk_id` values must belong to the retrieved context for that request
- citation offsets must stay within the retrieved chunk text length and stored chunk bounds

Structured refusals are validated against these rules:

- `refusal.is_refusal=true` requires `final_answer` to match `refusal.message`
- refusal text must not contain citation markers
- refusal text must look like a refusal rather than a substantive supported answer claim

## Validator outcomes

The backend-facing outcome enum is:

- `valid` — accept the response as-is
- `retry` — regenerate because the answer shape or citation mapping is malformed
- `refuse` — convert the response into an explicit refusal because it contradicts the refusal contract

## Failure codes

Current machine-readable failure codes:

- `missing_citation_coverage`
- `malformed_citation_marker`
- `unknown_citation_marker`
- `duplicate_citation_marker`
- `non_retrieved_chunk`
- `offset_out_of_range`
- `refusal_answer_contradiction`

## Checked-in smoke fixtures

The smoke command uses these checked-in fixtures:

- `docs/contracts/query_response.answer.example.json`
- `docs/contracts/query_response.refusal.example.json`
- `docs/contracts/query_response.retrieved_context.example.json`

## Exact local smoke command

```bash
uv run python -m supportdoc_rag_chatbot smoke-citation-validator \
  --answer-fixture docs/contracts/query_response.answer.example.json \
  --refusal-fixture docs/contracts/query_response.refusal.example.json \
  --retrieved-context docs/contracts/query_response.retrieved_context.example.json
```

This validates the checked-in supported-answer fixture against deterministic retrieved-context metadata and confirms the checked-in refusal fixture remains a valid refusal.
