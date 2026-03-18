from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup, Tag

from .jsonl import read_jsonl
from .schemas import ManifestRecord, SectionRecord

MARKDOWN_SUFFIXES = {".md", ".mdx"}
HTML_SUFFIXES = {".html", ".htm"}

FRONT_MATTER_BOUNDARY_RE = re.compile(r"^---\s*$")
FRONT_MATTER_FIELD_RE = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*:\s*["\']?(.*?)["\']?\s*$')
HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
LINK_RE = re.compile(r"!\[(.*?)\]\([^\)]*\)|\[(.*?)\]\([^\)]*\)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
EMPHASIS_RE = re.compile(r"(?<!\*)\*\*(.*?)\*\*|__(.*?)__|(?<!\*)\*(.*?)\*|_(.*?)_")
HTML_TAG_RE = re.compile(r"<[^>]+>")
ORDERED_LIST_RE = re.compile(r"^\s*\d+\.\s+")
UNORDERED_LIST_RE = re.compile(r"^\s*[-+*]\s+")
MULTI_BLANK_RE = re.compile(r"\n{3,}")

HTML_HEADING_LEVELS = {f"h{level}": level for level in range(1, 7)}
HTML_SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside"}
HTML_BLOCK_TAGS = {"p", "li", "pre", "blockquote", "code"}


@dataclass(slots=True)
class _SectionSeed:
    heading: str | None
    section_path: list[str]
    text: str


def strip_front_matter(text: str) -> str:
    body, _ = split_front_matter(text)
    return body


def split_front_matter(text: str) -> tuple[str, dict[str, str]]:
    normalized = _normalize_newlines(text)
    lines = normalized.split("\n")
    if not lines or not FRONT_MATTER_BOUNDARY_RE.match(lines[0]):
        return normalized, {}

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if FRONT_MATTER_BOUNDARY_RE.match(line) or line.strip() == "...":
            closing_index = index
            break

    if closing_index is None:
        return normalized, {}

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        match = FRONT_MATTER_FIELD_RE.match(line)
        if match is not None:
            metadata[match.group(1).lower()] = match.group(2).strip()

    body = "\n".join(lines[closing_index + 1 :])
    return body, metadata


def _strip_markdown_markup(text: str) -> str:
    text = LINK_RE.sub(lambda match: match.group(1) or match.group(2) or "", text)
    text = INLINE_CODE_RE.sub(lambda match: match.group(1), text)
    text = EMPHASIS_RE.sub(
        lambda match: next(group for group in match.groups() if group is not None),
        text,
    )
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("\\", "")
    return text


def _normalize_plain_text(text: str, *, preserve_line_breaks: bool = False) -> str:
    normalized = htmllib.unescape(_normalize_newlines(text)).replace("\xa0", " ")
    cleaned_lines: list[str] = []

    for raw_line in normalized.split("\n"):
        line = re.sub(
            r"[ \t]+", " ", raw_line.rstrip() if preserve_line_breaks else raw_line.strip()
        )
        if not preserve_line_breaks:
            line = re.sub(r"\s+([,.;:!?])", r"\1", line)
            line = line.strip()
        cleaned_lines.append(line)

    collapsed_lines: list[str] = []
    previous_blank = False
    for line in cleaned_lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        collapsed_lines.append(line if preserve_line_breaks else line.strip())
        previous_blank = is_blank

    return "\n".join(collapsed_lines).strip()


def normalize_markdown(markdown_text: str) -> str:
    lines: list[str] = []
    for raw_line in _normalize_newlines(markdown_text).split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            lines.append("")
            continue
        if FENCE_RE.match(stripped):
            continue

        heading_match = HEADING_RE.match(stripped)
        line = heading_match.group("text") if heading_match is not None else raw_line
        line = ORDERED_LIST_RE.sub("", line)
        line = UNORDERED_LIST_RE.sub("", line)
        if line.lstrip().startswith(">"):
            line = line.lstrip()[1:].lstrip()
        lines.append(_strip_markdown_markup(line))

    text = "\n".join(lines).strip()
    return MULTI_BLANK_RE.sub("\n\n", _normalize_plain_text(text))


def _normalize_html_text(html_text: str) -> str:
    if not html_text.strip():
        return ""

    soup = BeautifulSoup(html_text, "lxml")
    for tag in soup.find_all(HTML_SKIP_TAGS):
        tag.decompose()

    blocks: list[str] = []
    for tag in soup.find_all(list(HTML_HEADING_LEVELS) + sorted(HTML_BLOCK_TAGS)):
        if not _is_top_level_content_tag(tag):
            continue
        if tag.name == "pre":
            raw_text = tag.get_text("\n", strip=False)
            normalized = _normalize_plain_text(raw_text, preserve_line_breaks=True)
        else:
            raw_text = tag.get_text(" ", strip=True)
            normalized = _normalize_plain_text(raw_text)
        if normalized:
            blocks.append(normalized)

    if blocks:
        return "\n\n".join(blocks)

    return _normalize_plain_text(soup.get_text(" ", strip=True))


def _fallback_title(source_path: str) -> str:
    stem = Path(source_path).stem
    parts = [part for part in re.split(r"[-_]+", stem) if part]
    return " ".join(part.capitalize() for part in parts) or stem


def _compose_section_path(title_prefix: list[str], heading_stack: list[str]) -> list[str]:
    path: list[str] = []
    for part in [*title_prefix, *heading_stack]:
        normalized = _normalize_plain_text(part)
        if not normalized:
            continue
        if not path or path[-1] != normalized:
            path.append(normalized)
    return path


def _append_seed(
    seeds: list[_SectionSeed],
    *,
    heading: str | None,
    section_path: list[str],
    text: str,
) -> None:
    normalized = _normalize_plain_text(text, preserve_line_breaks="\n" in text)
    if not normalized:
        return
    seeds.append(
        _SectionSeed(
            heading=_normalize_plain_text(heading) if heading is not None else None,
            section_path=section_path,
            text=normalized,
        )
    )


def _extract_markdown_title(body: str, metadata: dict[str, str], fallback_title: str) -> str:
    title = _normalize_plain_text(metadata.get("title", ""))
    if title:
        return title

    in_code_fence = False
    active_fence = ""
    for raw_line in _normalize_newlines(body).split("\n"):
        stripped = raw_line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence_token = stripped[:3]
            if in_code_fence and stripped.startswith(active_fence):
                in_code_fence = False
                active_fence = ""
            else:
                in_code_fence = True
                active_fence = fence_token
            continue
        if in_code_fence:
            continue

        match = HEADING_RE.match(stripped)
        if match is not None and len(match.group("level")) == 1:
            return _normalize_plain_text(_strip_markdown_markup(match.group("text")))

    return _normalize_plain_text(fallback_title) or "Untitled Document"


def _parse_markdown_document(text: str, *, record: ManifestRecord) -> list[_SectionSeed]:
    body, metadata = split_front_matter(text)
    doc_title = _extract_markdown_title(body, metadata, _fallback_title(record.source_path))
    title_prefix = [doc_title] if doc_title else []

    heading_stack: list[str] = []
    buffer: list[str] = []
    seeds: list[_SectionSeed] = []
    in_code_fence = False
    active_fence = ""

    def flush() -> None:
        normalized = normalize_markdown("\n".join(buffer))
        if normalized:
            _append_seed(
                seeds,
                heading=heading_stack[-1] if heading_stack else None,
                section_path=_compose_section_path(title_prefix, heading_stack),
                text=normalized,
            )

    for raw_line in _normalize_newlines(body).split("\n"):
        stripped = raw_line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence_token = stripped[:3]
            if in_code_fence and stripped.startswith(active_fence):
                in_code_fence = False
                active_fence = ""
            else:
                in_code_fence = True
                active_fence = fence_token
            buffer.append(raw_line)
            continue

        if not in_code_fence:
            match = HEADING_RE.match(stripped)
            if match is not None:
                flush()
                heading_text = _normalize_plain_text(_strip_markdown_markup(match.group("text")))
                if heading_text:
                    level = len(match.group("level"))
                    heading_stack[:] = heading_stack[: level - 1] + [heading_text]
                buffer = []
                continue

        buffer.append(raw_line)

    flush()

    if seeds:
        return seeds

    fallback_text = normalize_markdown(body)
    if not fallback_text:
        return []

    return [
        _SectionSeed(
            heading=None,
            section_path=[doc_title],
            text=fallback_text,
        )
    ]


def _parse_html_document(text: str, *, record: ManifestRecord) -> list[_SectionSeed]:
    soup = BeautifulSoup(text, "lxml")
    for tag in soup.find_all(HTML_SKIP_TAGS):
        tag.decompose()

    body = soup.body or soup
    title = _normalize_plain_text(
        soup.title.get_text(" ", strip=True) if soup.title is not None else ""
    )
    if not title:
        first_heading = body.find(["h1", "h2"])
        title = _normalize_plain_text(
            first_heading.get_text(" ", strip=True) if first_heading is not None else ""
        )
    if not title:
        title = _fallback_title(record.source_path)

    title_prefix = [title] if title else []
    heading_stack: list[str] = []
    buffer: list[str] = []
    seeds: list[_SectionSeed] = []

    def flush() -> None:
        normalized = _normalize_html_text("".join(buffer))
        if normalized:
            _append_seed(
                seeds,
                heading=heading_stack[-1] if heading_stack else None,
                section_path=_compose_section_path(title_prefix, heading_stack),
                text=normalized,
            )

    ordered_tags = body.find_all(list(HTML_HEADING_LEVELS) + sorted(HTML_BLOCK_TAGS))
    for tag in ordered_tags:
        if not _is_top_level_content_tag(tag):
            continue

        if tag.name in HTML_HEADING_LEVELS:
            flush()
            level = HTML_HEADING_LEVELS[tag.name]
            heading_text = _normalize_plain_text(tag.get_text(" ", strip=True))
            if heading_text:
                heading_stack[:] = heading_stack[: level - 1] + [heading_text]
            buffer = []
            continue

        buffer.append(str(tag))

    flush()

    if seeds:
        return seeds

    fallback_text = _normalize_html_text(str(body))
    if not fallback_text:
        return []

    return [
        _SectionSeed(
            heading=None,
            section_path=[title],
            text=fallback_text,
        )
    ]


def parse_document(record: ManifestRecord, *, snapshot_root: Path) -> list[SectionRecord]:
    source_file = snapshot_root / record.source_path
    if not source_file.exists():
        raise FileNotFoundError(f"Missing source file for manifest entry: {source_file}")

    raw_text = source_file.read_text(encoding="utf-8")
    suffix = source_file.suffix.lower()
    if suffix in HTML_SUFFIXES:
        seeds = _parse_html_document(raw_text, record=record)
    else:
        seeds = _parse_markdown_document(raw_text, record=record)

    if not seeds:
        raise ValueError(f"Document {record.doc_id} produced no non-empty sections")

    doc_title = (
        seeds[0].section_path[0] if seeds[0].section_path else _fallback_title(record.source_path)
    )
    sections: list[SectionRecord] = []
    cursor = 0

    for section_index, seed in enumerate(seeds):
        text = seed.text.strip()
        if not text:
            continue

        start_offset = cursor
        end_offset = start_offset + len(text)
        cursor = end_offset + 2

        sections.append(
            SectionRecord(
                snapshot_id=record.snapshot_id,
                doc_id=record.doc_id,
                section_id=f"{record.doc_id}-sec-{section_index:04d}",
                section_index=section_index,
                doc_title=doc_title,
                heading=seed.heading,
                section_path=seed.section_path or [doc_title],
                source_path=record.source_path,
                source_url=record.source_url,
                license=record.license,
                attribution=record.attribution,
                language=record.language,
                start_offset=start_offset,
                end_offset=end_offset,
                text=text,
            )
        )

    if not sections:
        raise ValueError(f"Document {record.doc_id} produced no non-empty sections")

    return sections


def parse_manifest(manifest_path: Path, *, snapshot_root: Path) -> Iterator[SectionRecord]:
    records = sorted(
        (ManifestRecord.from_dict(payload) for payload in read_jsonl(manifest_path)),
        key=lambda record: (record.source_path, record.doc_id),
    )

    for record in records:
        if not record.allowed:
            continue
        yield from parse_document(record, snapshot_root=snapshot_root)


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _is_top_level_content_tag(tag: Tag) -> bool:
    parent = tag.parent
    while isinstance(parent, Tag):
        if parent.name in HTML_BLOCK_TAGS or parent.name in HTML_HEADING_LEVELS:
            return False
        parent = parent.parent
    return True
