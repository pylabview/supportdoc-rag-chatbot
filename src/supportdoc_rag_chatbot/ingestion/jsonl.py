from __future__ import annotations

import json
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


def _normalize_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()
    if is_dataclass(record):
        from dataclasses import asdict

        return asdict(record)
    if isinstance(record, dict):
        return record
    raise TypeError(f"Unsupported JSONL record type: {type(record)!r}")


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                yield json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} on line {line_number}") from exc


def write_jsonl(path: Path, records: Iterable[Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_normalize_record(record), ensure_ascii=False) + "\n")
            count += 1
    return count
