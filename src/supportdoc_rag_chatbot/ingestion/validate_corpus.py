from __future__ import annotations

import argparse
from pathlib import Path

from .validator import build_ingest_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate ingestion artifacts and emit ingest_report.json"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--sections", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    parser.add_argument(
        "--allow-errors",
        action="store_true",
        help="Write the report and exit zero even if validation errors are present.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = build_ingest_report(
        manifest_path=args.manifest,
        sections_path=args.sections,
        chunks_path=args.chunks,
        output_path=args.report_out,
    )

    if report.errors:
        print(f"Validation finished with {len(report.errors)} error(s). Report: {args.report_out}")
        if not args.allow_errors:
            raise SystemExit(1)
    else:
        print(f"Validation passed. Report: {args.report_out}")


if __name__ == "__main__":
    main()
