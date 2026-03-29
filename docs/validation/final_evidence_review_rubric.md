# Final evidence review rubric

Use this rubric for the artifact-backed MVP trust pass.

## Supported-answer verdict rules

Mark a supported answer as **pass** only when all of these are true:

- every substantive claim is supported by the cited chunk text from the reviewed run
- every citation in the accepted answer maps to a retrieved chunk for that request
- the answer does not add unsupported claims, outside knowledge, or stronger wording than the evidence supports
- the response keeps the canonical non-refusal shape (`refusal.is_refusal=false` and at least one citation)

Mark it as **blocker fail** when any cited answer includes unsupported claims, missing support, bad citation mapping, or answer text that should have been refused instead.

## Refusal verdict rules

Mark a refusal as **pass** only when all of these are true:

- the response uses the expected canonical refusal reason code for the case
- `final_answer` matches `refusal.message`
- `citations` is empty
- the refusal does not contain substantive unsupported answer text

Mark it as **blocker fail** when a should-refuse case leaks unsupported answer content, uses the wrong refusal class, or returns a non-refusal answer without adequate support.

## Defect types

Use one or more of these labels when a case fails:

- `retrieval_miss`
- `weak_evidence`
- `overclaiming`
- `bad_citation_mapping`
- `wrong_refusal`
- `false_refusal`
- `other`

Treat `overclaiming`, `bad_citation_mapping`, and any refusal leakage as blocker-level trust defects for MVP readiness.

## Review notes expectations

Each reviewed case should record:

- the observed outcome
- a pass/fail verdict
- brief reviewer notes explaining why the verdict was assigned
- any defect types if the case failed

## Sample-level summary

The final reviewed summary should report at least:

- supported cases accepted / reviewed
- citation-correct supported cases / reviewed supported cases
- refusal-correct cases / reviewed refusal cases
- blocker-level defects remaining
- any known non-blocking limitations
