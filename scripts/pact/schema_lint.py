#!/usr/bin/env python3
"""Fail when PACT schemas use keywords the stdlib validator does not implement."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / ".pact" / "schema"

SUPPORTED_VALIDATION = {
    "$ref",
    "type",
    "required",
    "additionalProperties",
    "properties",
    "$defs",
    "enum",
    "const",
    "oneOf",
    "allOf",
    "if",
    "then",
    "minLength",
    "pattern",
    "minimum",
    "maximum",
    "minItems",
    "uniqueItems",
    "items",
}

ANNOTATIONS = {
    "$schema",
    "$id",
    "$comment",
    "title",
    "description",
    "default",
    "examples",
}

ALLOWED = SUPPORTED_VALIDATION | ANNOTATIONS
SUPPORTED_TYPES = {
    "object",
    "array",
    "string",
    "integer",
    "number",
    "boolean",
    "null",
}


def pointer_get(root: dict, ref: str):
    if not ref.startswith("#/"):
        raise ValueError(f"non-local $ref is unsupported: {ref}")
    node = root
    for raw in ref[2:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"unresolvable local $ref: {ref}")
        node = node[part]
    return node


def lint_schema_node(
    node,
    *,
    root: dict,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(node, dict):
        errors.append(f"{path}: schema node must be an object")
        return

    unknown = sorted(set(node) - ALLOWED)
    for key in unknown:
        errors.append(
            f"{path}: unsupported schema keyword {key!r}; "
            "PACT runtime would not enforce it"
        )

    if "$ref" in node:
        try:
            target = pointer_get(root, node["$ref"])
            if not isinstance(target, dict):
                errors.append(f"{path}: $ref target is not a schema object")
        except (TypeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")

    if "type" in node:
        values = node["type"] if isinstance(node["type"], list) else [node["type"]]
        for value in values:
            if value not in SUPPORTED_TYPES:
                errors.append(f"{path}: unsupported schema type {value!r}")

    if "properties" in node:
        props = node["properties"]
        if not isinstance(props, dict):
            errors.append(f"{path}.properties: must be an object")
        else:
            for name, child in props.items():
                lint_schema_node(
                    child,
                    root=root,
                    path=f"{path}.properties.{name}",
                    errors=errors,
                )

    if "$defs" in node:
        defs = node["$defs"]
        if not isinstance(defs, dict):
            errors.append(f"{path}.$defs: must be an object")
        else:
            for name, child in defs.items():
                lint_schema_node(
                    child,
                    root=root,
                    path=f"{path}.$defs.{name}",
                    errors=errors,
                )

    for key in ("items", "additionalProperties", "if", "then"):
        child = node.get(key)
        if isinstance(child, dict):
            lint_schema_node(
                child,
                root=root,
                path=f"{path}.{key}",
                errors=errors,
            )

    for key in ("oneOf", "allOf"):
        children = node.get(key)
        if children is None:
            continue
        if not isinstance(children, list):
            errors.append(f"{path}.{key}: must be an array of schemas")
            continue
        for index, child in enumerate(children):
            lint_schema_node(
                child,
                root=root,
                path=f"{path}.{key}[{index}]",
                errors=errors,
            )


def lint_file(path: pathlib.Path) -> list[str]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path.name}: cannot parse JSON schema: {exc}"]

    errors: list[str] = []
    lint_schema_node(
        schema,
        root=schema,
        path=path.name,
        errors=errors,
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate that PACT schemas use only runtime-supported keywords"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="schema files; defaults to all .pact/schema/*.json",
    )
    args = parser.parse_args()

    paths = [
        pathlib.Path(value).expanduser().resolve()
        for value in args.paths
    ] if args.paths else sorted(SCHEMA_DIR.glob("*.json"))

    errors: list[str] = []
    for path in paths:
        errors.extend(lint_file(path))

    if errors:
        print(f"PACT schema-lint: {len(errors)} error(s)", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"PACT schema-lint: {len(paths)} schema file(s) supported by runtime validator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
