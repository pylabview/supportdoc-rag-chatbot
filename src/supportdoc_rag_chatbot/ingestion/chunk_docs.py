from __future__ import annotations

import argparse
from pathlib import Path

from .chunker import chunk_sections
from .jsonl import read_jsonl, write_jsonl
from .schemas import SectionRecord


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chunk sections.jsonl into chunks.jsonl")
    parser.add_argument("--input", required=True, type=Path, help="Path to sections.jsonl")
    parser.add_argument("--output", required=True, type=Path, help="Path to chunks.jsonl")
    parser.add_argument("--max-tokens", type=int, default=350)
    parser.add_argument("--overlap-tokens", type=int, default=50)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    sections = [SectionRecord.from_dict(payload) for payload in read_jsonl(args.input)]
    chunks = list(
        chunk_sections(
            sections,
            max_tokens=args.max_tokens,
            overlap_tokens=args.overlap_tokens,
        )
    )
    count = write_jsonl(args.output, chunks)
    print(f"Wrote {count} chunks to {args.output}")


if __name__ == "__main__":
    main()
