from __future__ import annotations

import hashlib
import re
from typing import Iterable, Iterator

from .schemas import ChunkRecord, SectionRecord

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_token_count(text: str) -> int:
    return len(list(TOKEN_RE.finditer(text)))


def _token_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in TOKEN_RE.finditer(text)]


def _stable_chunk_id(section: SectionRecord, *, chunk_index: int, start: int, end: int) -> str:
    digest = hashlib.sha1(
        f"{section.snapshot_id}|{section.doc_id}|{section.section_id}|{chunk_index}|{start}|{end}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    return f"{section.doc_id}-chk-{chunk_index:04d}-{digest}"


def chunk_section(
    section: SectionRecord,
    *,
    max_tokens: int = 350,
    overlap_tokens: int = 50,
) -> list[ChunkRecord]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be >= 0")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    spans = _token_spans(section.text)
    if not spans:
        return []

    chunks: list[ChunkRecord] = []
    start_index = 0
    chunk_index = 0

    while start_index < len(spans):
        end_index = min(start_index + max_tokens, len(spans))
        start_char = spans[start_index][0]
        end_char = spans[end_index - 1][1]
        chunk_text = section.text[start_char:end_char].strip()

        if chunk_text:
            chunks.append(
                ChunkRecord(
                    snapshot_id=section.snapshot_id,
                    doc_id=section.doc_id,
                    chunk_id=_stable_chunk_id(
                        section,
                        chunk_index=chunk_index,
                        start=section.start_offset + start_char,
                        end=section.start_offset + end_char,
                    ),
                    section_id=section.section_id,
                    section_index=section.section_index,
                    chunk_index=chunk_index,
                    doc_title=section.doc_title,
                    section_path=section.section_path,
                    source_path=section.source_path,
                    source_url=section.source_url,
                    license=section.license,
                    attribution=section.attribution,
                    language=section.language,
                    start_offset=section.start_offset + start_char,
                    end_offset=section.start_offset + end_char,
                    token_count=end_index - start_index,
                    text=chunk_text,
                )
            )
            chunk_index += 1

        if end_index >= len(spans):
            break

        next_start = end_index - overlap_tokens
        if next_start <= start_index:
            next_start = start_index + 1
        start_index = next_start

    return chunks


def chunk_sections(
    sections: Iterable[SectionRecord],
    *,
    max_tokens: int = 350,
    overlap_tokens: int = 50,
) -> Iterator[ChunkRecord]:
    for section in sections:
        yield from chunk_section(section, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
