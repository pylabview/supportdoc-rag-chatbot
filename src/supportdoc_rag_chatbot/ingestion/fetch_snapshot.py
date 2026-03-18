from __future__ import annotations

import argparse
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stub for future snapshot acquisition automation.")
    parser.add_argument("--repo-url", default="https://github.com/kubernetes/website.git")
    parser.add_argument("--ref", required=True, help="Pinned git commit, tag, or branch")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    raise SystemExit(
        "fetch_snapshot is intentionally left as a stub for the separate downloader/fetcher task. "
        f"Requested ref={args.ref!r}, output_dir={str(args.output_dir)!r}."
    )


if __name__ == "__main__":
    main()
