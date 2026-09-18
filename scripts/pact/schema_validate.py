"""Small stdlib-only validator for the JSON Schema subset used by PACT.

PACT keeps JSON Schema files as protocol documentation. Runtime validation only
implements the keywords PACT itself uses; this is intentionally not a general
JSON Schema implementation.
"""

from __future__ import annotations

import json
import re
from typing import Any


class SchemaValidationError(ValueError):
    pass


def _resolve_ref(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"unsupported non-local $ref: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaValidationError(f"unresolvable $ref: {ref}")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaValidationError(f"$ref does not resolve to an object schema: {ref}")
    return node


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaValidationError(f"unsupported schema type: {expected}")


def _is_unique(values: list[Any]) -> bool:
    seen: set[str] = set()
    for value in values:
        try:
            key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        except TypeError:
            key = repr(value)
        if key in seen:
            return False
        seen.add(key)
    return True


def _path_text(path: tuple[Any, ...]) -> str:
    return ".".join(str(p) for p in path) if path else "<root>"


def _validate(
    value: Any,
    schema: dict,
    root: dict,
    path: tuple[Any, ...],
    errors: list[str],
) -> None:
    if "$ref" in schema:
        _validate(value, _resolve_ref(root, schema["$ref"]), root, path, errors)
        return

    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            candidate_errors: list[str] = []
            _validate(value, candidate, root, path, candidate_errors)
            if not candidate_errors:
                matches += 1
        if matches != 1:
            errors.append(f"{_path_text(path)}: expected exactly one oneOf schema to match")
        return

    if "allOf" in schema:
        for candidate in schema["allOf"]:
            if_schema = candidate.get("if")
            then_schema = candidate.get("then")
            if if_schema is not None and then_schema is not None:
                condition_errors: list[str] = []
                _validate(value, if_schema, root, path, condition_errors)
                if not condition_errors:
                    _validate(value, then_schema, root, path, errors)
            else:
                _validate(value, candidate, root, path, errors)

    if "const" in schema and value != schema["const"]:
        errors.append(f"{_path_text(path)}: expected constant {schema['const']!r}")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            f"{_path_text(path)}: expected one of {schema['enum']!r}, got {value!r}"
        )
        return

    if "type" in schema:
        expected = schema["type"]
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, item) for item in allowed):
            errors.append(
                f"{_path_text(path)}: expected type {allowed!r}, "
                f"got {type(value).__name__}"
            )
            return

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            errors.append(
                f"{_path_text(path)}: string length must be >= {min_length}"
            )
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            errors.append(
                f"{_path_text(path)}: value {value!r} does not match {pattern!r}"
            )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{_path_text(path)}: value must be >= {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{_path_text(path)}: value must be <= {maximum}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{_path_text(path)}: array requires at least {min_items} item(s)")
        if schema.get("uniqueItems") and not _is_unique(value):
            errors.append(f"{_path_text(path)}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item, item_schema, root, path + (index,), errors)

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{_path_text(path)}: missing required property {key!r}")

        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], root, path + (key,), errors)
                continue

            additional = schema.get("additionalProperties", True)
            if additional is False:
                errors.append(f"{_path_text(path)}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                _validate(item, additional, root, path + (key,), errors)


def validate_instance(value: Any, schema: dict) -> list[str]:
    errors: list[str] = []
    _validate(value, schema, schema, (), errors)
    return errors


def load_schema(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
