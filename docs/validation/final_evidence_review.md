# Final evidence review (artifact-backed API trust pass)

This document records the reviewed evidence correctness pass for the MVP against the artifact-backed `/query` path.

## Inputs

- review set: `data/evaluation/final_evidence_review.k8s-9e1e32b.v1.jsonl`
- review set metadata: `data/evaluation/final_evidence_review.k8s-9e1e32b.v1.metadata.json`
- rubric: `docs/validation/final_evidence_review_rubric.md`
- results template: `docs/validation/final_evidence_review_results.template.md`
- first-pass raw outputs: `docs/validation/final_evidence_review.first_pass.raw.json`
- final-pass raw outputs: `docs/validation/final_evidence_review.final_pass.raw.json`

## Reviewed backend path

The reviewed run uses the real FastAPI `POST /query` surface with:

- retrieval mode: `artifact`
- generation mode: `fixture`
- retriever: `dense-artifact-retriever`
- artifact fixture: a deterministic two-chunk Pods excerpt tied to snapshot `k8s-9e1e32b`

This pass is intentionally artifact-backed rather than retrieval-harness-only so the review covers retrieval sufficiency, prompting, refusal handling, citation validation, and API serialization together.

## First pass review results

| case_id | expected | observed | verdict | defect types | reviewer notes |
| --- | --- | --- | --- | --- | --- |
| `pod-definition-supported` | supported answer | supported answer | pass | none | The answer stayed within the cited Pod definition chunk and did not add unsupported claims beyond the `[1]` evidence span. |
| `pod-storage-insufficient-evidence` | refusal (`insufficient_evidence`) | refusal (`insufficient_evidence`) | pass | none | The backend retrieved Pod-related chunks but only one hit cleared the support threshold, so the canonical insufficient-evidence refusal was appropriate and leak-free. |
| `bios-reset-no-relevant-docs` | refusal (`no_relevant_docs`) | refusal (`no_relevant_docs`) | pass | none | Retrieval stayed below the no-hit floor and the backend returned the canonical no-relevant-docs refusal with empty citations and no substantive answer text. |

## Defect classification

No blocker-level evidence defects were found in the reviewed sample.

Observed blocker counts in the first reviewed pass:

- `retrieval_miss`: 0
- `weak_evidence`: 0
- `overclaiming`: 0
- `bad_citation_mapping`: 0
- `wrong_refusal`: 0
- `false_refusal`: 0
- `other`: 0

## Changes between the first and final pass

No backend code changes were required between passes. The first reviewed pass already met the rubric, so the final pass reran the same review set to capture a stable closeout artifact for MVP readiness.

## Final pass summary

- reviewed cases: `3`
- supported cases accepted: `1 / 1`
- citation-correct supported cases: `1 / 1`
- refusal-correct cases: `2 / 2`
- blocker-level defects remaining: `0`

These are the sample-level evidence outcomes needed for the MVP story: the accepted supported answer in the reviewed sample was citation-correct, and every reviewed should-refuse case returned a canonical refusal without unsupported answer leakage.

## Known limitations

- The reviewed set is intentionally small and is not a substitute for a larger corpus-wide evaluation.
- Generation is still fixture-backed for this pass, so the review validates trust orchestration against deterministic outputs rather than a live model backend.
- The artifact fixture is a minimal two-chunk excerpt tied to the approved snapshot; it proves the artifact-backed API path, but it does not exercise every retrieval edge case in the full corpus.
