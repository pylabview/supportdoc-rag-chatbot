# Retrieval dev QA set

This document explains the committed development QA set used for retrieval-only baseline work in Epic 4.

## Files

The current versioned dataset lives in `data/evaluation/`:

- `dev_qa.k8s-9e1e32b.v1.jsonl` - one JSON object per query
- `dev_qa.k8s-9e1e32b.v1.metadata.json` - dataset-level metadata
- `dev_qa.k8s-9e1e32b.v1.registry.json` - valid doc, section, and chunk IDs for the same snapshot

## Query row schema

Each JSONL row includes:

- `query_id`: stable identifier for the query
- `snapshot_id`: corpus snapshot label the row was annotated against
- `question`: natural-language retrieval query
- `answerable`: whether the approved corpus contains enough evidence to answer the question
- `category`: coarse bucket such as `definition`, `how-to`, `troubleshooting`, or `insufficient-evidence`
- `tags`: optional retrieval-oriented tags
- `doc_ids`: relevant document IDs when known
- `expected_section_ids`: acceptable section-level evidence IDs
- `expected_chunk_ids`: acceptable chunk-level evidence IDs
- `notes`: annotation guidance for edge cases and acceptable alternatives

For `answerable=true`, at least one expected section or chunk ID must be present.

For `answerable=false`, both expected-ID lists should be empty. These rows are intentionally included so retrieval baselines can be checked for false-positive evidence surfacing.

## Annotation rules

Use these rules when extending the dataset:

1. Prefer natural user questions over benchmark-style keyword prompts.
2. Prefer stable chunk references whenever chunk-level evidence is available and unambiguous.
3. Include section IDs alongside chunk IDs when a broader section is still an acceptable match.
4. Mark a row as unanswerable when the approved snapshot does not contain enough evidence to support the query, even if the answer is widely known elsewhere.
5. Keep notes short, but use them to record acceptable alternative evidence when a single chunk would be too narrow.

## Validation workflow

The helper module `src/supportdoc_rag_chatbot/evaluation/dev_qa.py` provides:

- dataset loading
- metadata loading
- evidence-registry loading
- structural validation of the dataset against the committed snapshot registry
- optional rebuilding of a registry from `sections.jsonl` and `chunks.jsonl`

Typical usage from the repo root:

```bash
python - <<'PY'
from supportdoc_rag_chatbot.evaluation import (
    load_default_dev_qa_dataset,
    load_default_dev_qa_metadata,
    load_default_evidence_registry,
    validate_dev_qa_dataset,
)

entries = load_default_dev_qa_dataset()
metadata = load_default_dev_qa_metadata()
registry = load_default_evidence_registry()

validate_dev_qa_dataset(entries=entries, metadata=metadata, registry=registry)
print(f"validated {len(entries)} retrieval QA rows")
PY
```

## Snapshot tie-in

This version is tied to the committed manifest at `data/manifests/source_manifest.jsonl` and snapshot `k8s-9e1e32b`.

If the approved corpus snapshot changes, create a new versioned QA artifact and matching registry rather than mutating the existing one in place.
