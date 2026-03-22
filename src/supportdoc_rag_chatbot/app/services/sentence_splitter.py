from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_BULLET_LINE_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])\s+\S")
_COMMON_ABBREVIATION_SUFFIXES = (
    "e.g.",
    "i.e.",
    "etc.",
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "vs.",
)


class ClaimKind(StrEnum):
    """Deterministic answer-unit categories for citation coverage checks."""

    SENTENCE = "sentence"
    BULLET = "bullet"


@dataclass(slots=True, frozen=True)
class ClaimSpan:
    """One sentence or bullet item extracted from a generated answer."""

    kind: ClaimKind
    text: str
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("ClaimSpan.text must not be blank")
        if self.start_offset < 0:
            raise ValueError("ClaimSpan.start_offset must be >= 0")
        if self.end_offset <= self.start_offset:
            raise ValueError("ClaimSpan.end_offset must be greater than start_offset")


def split_answer_claims(answer_text: str) -> tuple[ClaimSpan, ...]:
    """Split answer text into deterministic sentence and bullet-item spans."""

    if not answer_text.strip():
        return ()

    spans: list[ClaimSpan] = []
    cursor = 0

    for raw_line in answer_text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            cursor += len(raw_line)
            continue

        if _BULLET_LINE_RE.match(line):
            bullet_span = _build_trimmed_span(
                line=line,
                base_offset=cursor,
                kind=ClaimKind.BULLET,
            )
            if bullet_span is not None:
                spans.append(bullet_span)
        else:
            spans.extend(_split_sentence_line(line, base_offset=cursor))

        cursor += len(raw_line)

    return tuple(spans)


def _split_sentence_line(line: str, *, base_offset: int) -> list[ClaimSpan]:
    spans: list[ClaimSpan] = []
    start_index = 0
    cursor = 0

    while cursor < len(line):
        character = line[cursor]
        if character in ".!?" and _is_sentence_boundary(line, punctuation_index=cursor):
            sentence = _build_trimmed_span(
                line=line,
                base_offset=base_offset,
                kind=ClaimKind.SENTENCE,
                segment_start=start_index,
                segment_end=cursor + 1,
            )
            if sentence is not None:
                spans.append(sentence)
            start_index = _skip_whitespace(line, cursor + 1)
            cursor = start_index
            continue
        cursor += 1

    tail = _build_trimmed_span(
        line=line,
        base_offset=base_offset,
        kind=ClaimKind.SENTENCE,
        segment_start=start_index,
        segment_end=len(line),
    )
    if tail is not None:
        spans.append(tail)
    return spans


def _is_sentence_boundary(line: str, *, punctuation_index: int) -> bool:
    next_index = punctuation_index + 1
    if next_index >= len(line):
        return True
    if not line[next_index].isspace():
        return False

    prefix = line[:next_index].lower().rstrip()
    if prefix.endswith(_COMMON_ABBREVIATION_SUFFIXES):
        return False
    return True


def _skip_whitespace(line: str, start_index: int) -> int:
    index = start_index
    while index < len(line) and line[index].isspace():
        index += 1
    return index


def _build_trimmed_span(
    *,
    line: str,
    base_offset: int,
    kind: ClaimKind,
    segment_start: int = 0,
    segment_end: int | None = None,
) -> ClaimSpan | None:
    if segment_end is None:
        segment_end = len(line)

    left = segment_start
    right = segment_end
    while left < right and line[left].isspace():
        left += 1
    while right > left and line[right - 1].isspace():
        right -= 1

    if left >= right:
        return None

    return ClaimSpan(
        kind=kind,
        text=line[left:right],
        start_offset=base_offset + left,
        end_offset=base_offset + right,
    )


__all__ = ["ClaimKind", "ClaimSpan", "split_answer_claims"]
