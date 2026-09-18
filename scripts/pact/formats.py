"""PACT stdlib-only configuration and metadata parsing.

New PACT files use TOML via Python 3.11+ tomllib. A deliberately small legacy
YAML reader remains for PACT 0.2 compatibility. It supports only the simple
mapping/list/scalar subset used by PACT-generated files; it is not a general
YAML parser.
"""

from __future__ import annotations

import ast
import pathlib
import re
import tomllib
from typing import Any


TOML_FRONT_MATTER = re.compile(r"\A\+\+\+\s*\n(.*?)\n\+\+\+\s*(?:\n|\Z)", re.DOTALL)
LEGACY_YAML_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


class FormatError(ValueError):
    pass


def load_toml(path: pathlib.Path) -> dict:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise FormatError(f"{path}: TOML root must be a table")
    return data


def _scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "none", "None", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            inner = value[1:-1].strip()
            return [] if not inner else [_scalar(part) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_legacy_yaml(text: str) -> dict:
    """Parse the restricted YAML subset emitted by PACT 0.2."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent]:
            raise FormatError("legacy YAML tabs are unsupported")
        lines.append((indent, raw.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    index = 0

    while index < len(lines):
        indent, content = lines[index]
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise FormatError("invalid legacy YAML indentation")
        parent = stack[-1][1]

        if content.startswith("- "):
            if not isinstance(parent, list):
                raise FormatError("legacy YAML list item without list parent")
            item_text = content[2:].strip()
            mapping = re.match(r"^([^:]+):(?:\s+|$)(.*)$", item_text)
            if mapping:
                key = mapping.group(1).strip()
                raw_value = mapping.group(2).strip()
                item: dict[str, Any] = {}
                item[key] = _scalar(raw_value)
                parent.append(item)
                stack.append((indent, item))
            else:
                parent.append(_scalar(item_text))
            index += 1
            continue

        if ":" not in content:
            raise FormatError(f"unsupported legacy YAML line: {content!r}")

        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not isinstance(parent, dict):
            raise FormatError("legacy YAML mapping entry without mapping parent")

        if raw_value:
            parent[key] = _scalar(raw_value)
            index += 1
            continue

        next_kind: Any = {}
        if index + 1 < len(lines):
            next_indent, next_content = lines[index + 1]
            if next_indent > indent and next_content.startswith("- "):
                next_kind = []
        parent[key] = next_kind
        stack.append((indent, next_kind))
        index += 1

    return root


def load_legacy_yaml(path: pathlib.Path) -> dict:
    data = parse_legacy_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FormatError(f"{path}: legacy YAML root must be a mapping")
    return data


def load_project_data(
    root: pathlib.Path,
    toml_relative: str,
    legacy_yaml_relative: str | None = None,
    *,
    strict: bool = True,
) -> tuple[dict, pathlib.Path, str]:
    toml_path = root / toml_relative
    if toml_path.exists():
        return load_toml(toml_path), toml_path, "toml"

    if legacy_yaml_relative:
        legacy_path = root / legacy_yaml_relative
        if legacy_path.exists():
            return load_legacy_yaml(legacy_path), legacy_path, "legacy-yaml"

    if strict:
        expected = toml_path
        raise FileNotFoundError(f"missing project configuration: {expected}")

    raise FileNotFoundError(toml_path)


def parse_markdown_metadata(raw: str) -> tuple[dict, str, str | None]:
    match = TOML_FRONT_MATTER.match(raw)
    if match:
        try:
            data = tomllib.loads(match.group(1))
        except tomllib.TOMLDecodeError as exc:
            raise FormatError(f"invalid TOML front matter: {exc}") from exc
        return data if isinstance(data, dict) else {}, raw[match.end():], "toml"

    match = LEGACY_YAML_FRONT_MATTER.match(raw)
    if match:
        data = parse_legacy_yaml(match.group(1))
        return data, raw[match.end():], "legacy-yaml"

    return {}, raw, None
