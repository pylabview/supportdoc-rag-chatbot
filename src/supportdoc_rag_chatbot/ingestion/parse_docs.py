from __future__ import annotations

import argparse
from pathlib import Path

from .jsonl import write_jsonl
from .parser import parse_manifest
from .schemas import SectionRecord


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Markdown/HTML docs into sections.jsonl")
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def build_sections_artifact(
    *,
    manifest_path: Path,
    snapshot_root: Path,
    output_path: Path,
) -> list[SectionRecord]:
    sections = list(parse_manifest(manifest_path, snapshot_root=snapshot_root))
    write_jsonl(output_path, sections)
    return sections


def main() -> None:
    args = build_arg_parser().parse_args()
    sections = build_sections_artifact(
        manifest_path=args.manifest,
        snapshot_root=args.snapshot_root,
        output_path=args.output,
    )
    print(f"Wrote {len(sections)} parsed sections to {args.output}")


if __name__ == "__main__":
    main()
