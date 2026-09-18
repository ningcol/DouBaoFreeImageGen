#!/usr/bin/env python3
"""Validate and expose the PACT Owner Profile."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from formats import load_legacy_yaml, load_toml
from schema_validate import load_schema, validate_instance


def load_config(root: pathlib.Path, strict: bool) -> tuple[dict, pathlib.Path, str, bool]:
    candidates = [
        (root / ".pact" / "config.toml", "toml", True),
        (root / ".pact" / "config.yaml", "legacy-yaml", True),
    ]
    if not strict:
        candidates.extend([
            (root / ".pact" / "config.example.toml", "toml", False),
            (root / ".pact" / "config.example.yaml", "legacy-yaml", False),
        ])

    for path, kind, configured in candidates:
        if not path.exists():
            continue
        data = load_toml(path) if kind == "toml" else load_legacy_yaml(path)
        return data, path, kind, configured

    raise FileNotFoundError(".pact/config.toml is missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read and validate the PACT Owner Profile")
    parser.add_argument("--root", help="repository root; defaults to this script's repository")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require project config.toml (legacy config.yaml remains readable)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    default_root = pathlib.Path(__file__).resolve().parents[2]
    root = pathlib.Path(args.root).expanduser().resolve() if args.root else default_root

    schema_path = root / ".pact" / "schema" / "config.schema.json"
    if not schema_path.exists():
        print(f"PACT owner: missing config schema at {schema_path}", file=sys.stderr)
        return 2

    try:
        config, source, source_format, configured = load_config(root, args.strict)
    except Exception as exc:
        print(f"PACT owner: {exc}", file=sys.stderr)
        return 2

    if source_format == "legacy-yaml":
        config = {
            "version": config.get("version", 1),
            "owner": config.get("owner", {}),
        }

    errors = validate_instance(config, load_schema(schema_path))
    if errors:
        print(f"PACT owner: invalid configuration in {source}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    owner = config["owner"]
    result = {
        "configured": configured,
        "source": source.relative_to(root).as_posix(),
        "source_format": source_format,
        "role": owner["role"],
        "language": owner["language"],
        "technical_depth": owner["technical_depth"],
        "communication": owner["communication"],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        state = "project config" if configured else "example fallback"
        print(f"PACT owner profile: {state}")
        print(f"- source: {result['source']} ({source_format})")
        print(f"- role: {result['role']}")
        print(f"- language: {result['language']}")
        print(f"- technical depth: {result['technical_depth']}")
        print(
            "- decision translation: "
            f"{result['communication']['decision_translation']}"
        )
        print(
            "- progressive disclosure: "
            f"{result['communication']['progressive_disclosure']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
