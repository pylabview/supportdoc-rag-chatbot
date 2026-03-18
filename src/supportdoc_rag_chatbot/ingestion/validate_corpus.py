from __future__ import annotations

import argparse
from pathlib import Path

from .validator import (
    load_chunk_records,
    load_manifest_records,
    load_section_records,
    validate_corpus,
    write_report,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate ingestion artifacts and emit ingest_report.json"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--sections", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when validation errors are present.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    manifest_records = load_manifest_records(args.manifest)
    sections = load_section_records(args.sections)
    chunks = load_chunk_records(args.chunks)
    report = validate_corpus(
        manifest_records,
        sections,
        chunks,
        manifest_path=args.manifest,
        sections_path=args.sections,
        chunks_path=args.chunks,
    )
    write_report(report, args.report_out)

    if report.errors:
        print(f"Validation finished with {len(report.errors)} error(s). Report: {args.report_out}")
        if args.strict:
            raise SystemExit(1)
    else:
        print(f"Validation passed. Report: {args.report_out}")


if __name__ == "__main__":
    main()
