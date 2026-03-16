#!/usr/bin/env python3
"""Generate a manifest of Kubernetes docs allowed into the RAG corpus."""

import argparse
import json
from pathlib import Path

ALLOWED_PREFIXES = [
    Path("content/en/docs/concepts"),
    Path("content/en/docs/tasks"),
    Path("content/en/docs/tutorials"),
    Path("content/en/docs/reference"),
]

DENIED_PREFIXES = [
    Path("content/en/blog"),
    Path("content/en/community"),
]

ALLOWED_SUFFIXES = {".md", ".mdx"}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def is_allowed(path: Path):
    if path.suffix not in ALLOWED_SUFFIXES:
        return False
    if any(path.is_relative_to(p) for p in DENIED_PREFIXES):
        return False
    return any(path.is_relative_to(p) for p in ALLOWED_PREFIXES)


def doc_id(path: Path):
    return "-".join(path.with_suffix("").parts)


def source_url(path: Path):
    parts = list(path.parts)
    idx = parts.index("docs")
    url_parts = parts[idx:]
    url_parts[-1] = path.stem
    return "https://kubernetes.io/" + "/".join(url_parts) + "/"


def main():
    args = parse_args()
    records = []

    for file in args.snapshot_root.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(args.snapshot_root)

        if not is_allowed(rel):
            continue

        records.append({
            "snapshot_id": args.snapshot_id,
            "source_path": rel.as_posix(),
            "source_url": source_url(rel),
            "doc_id": doc_id(rel),
            "language": "en",
            "license": "CC BY 4.0",
            "attribution": "Kubernetes Documentation © The Kubernetes Authors",
            "allowed": True
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"Generated {len(records)} manifest entries")


if __name__ == "__main__":
    main()
