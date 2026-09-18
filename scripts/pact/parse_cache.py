"""Per-file parse cache for disposable PACT indexes."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Callable
from typing import Any


def signature(path: pathlib.Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def load_cache(path: pathlib.Path, *, version: int) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": version, "entries": {}}

    if not isinstance(data, dict) or data.get("version") != version:
        return {"version": version, "entries": {}}

    entries = data.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return {"version": version, "entries": entries}


def save_cache(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_with_cache(
    *,
    root: pathlib.Path,
    paths: list[pathlib.Path],
    cache_path: pathlib.Path,
    cache_version: int,
    parser: Callable[[pathlib.Path], Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    old = load_cache(cache_path, version=cache_version)
    old_entries = old["entries"]
    new_entries: dict[str, dict] = {}
    parsed: dict[str, Any] = {}
    parsed_count = 0
    reused_count = 0

    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            current_signature = signature(path)
        except OSError:
            continue

        previous = old_entries.get(relative)
        if (
            isinstance(previous, dict)
            and previous.get("signature") == current_signature
            and "parsed" in previous
        ):
            value = previous["parsed"]
            reused_count += 1
        else:
            value = parser(path)
            parsed_count += 1

        parsed[relative] = value
        new_entries[relative] = {
            "signature": current_signature,
            "parsed": value,
        }

    save_cache(
        cache_path,
        {
            "version": cache_version,
            "entries": new_entries,
        },
    )
    return parsed, {
        "parsed": parsed_count,
        "reused": reused_count,
        "removed": max(len(old_entries) - len(new_entries), 0),
    }
