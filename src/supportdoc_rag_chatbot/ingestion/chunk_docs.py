from __future__ import annotations

import argparse
from pathlib import Path

from .chunker import chunk_sections
from .jsonl import read_jsonl, write_jsonl
from .schemas import ChunkRecord, SectionRecord


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chunk sections.jsonl into chunks.jsonl")
    parser.add_argument("--input", required=True, type=Path, help="Path to sections.jsonl")
    parser.add_argument("--output", required=True, type=Path, help="Path to chunks.jsonl")
    parser.add_argument("--max-tokens", type=int, default=350)
    parser.add_argument("--overlap-tokens", type=int, default=50)
    return parser


def build_chunks_artifact(
    *,
    sections_path: Path,
    output_path: Path,
    max_tokens: int = 350,
    overlap_tokens: int = 50,
) -> list[ChunkRecord]:
    sections = [SectionRecord.from_dict(payload) for payload in read_jsonl(sections_path)]
    chunks = list(
        chunk_sections(
            sections,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
    )
    write_jsonl(output_path, chunks)
    return chunks


def main() -> None:
    args = build_arg_parser().parse_args()
    chunks = build_chunks_artifact(
        sections_path=args.input,
        output_path=args.output,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    print(f"Wrote {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
    main()
