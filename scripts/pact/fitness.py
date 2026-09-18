#!/usr/bin/env python3
"""Run project-owned PACT architecture fitness functions."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

from formats import load_legacy_yaml, load_toml
from schema_validate import load_schema, validate_instance


def load_config(root: pathlib.Path, explicit: str | None, strict: bool):
    if explicit:
        path = pathlib.Path(explicit)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            raise FileNotFoundError(f"missing config at {path}")
        if path.suffix == ".toml":
            return load_toml(path), path, "toml", path.name == "fitness.toml"
        return load_legacy_yaml(path), path, "legacy-yaml", path.name == "fitness.yaml"

    candidates = [
        (root / ".pact" / "fitness.toml", "toml", True),
        (root / ".pact" / "fitness.yaml", "legacy-yaml", True),
    ]
    if not strict:
        candidates.extend([
            (root / ".pact" / "fitness.example.toml", "toml", False),
            (root / ".pact" / "fitness.example.yaml", "legacy-yaml", False),
        ])

    for path, kind, configured in candidates:
        if path.exists():
            data = load_toml(path) if kind == "toml" else load_legacy_yaml(path)
            return data, path, kind, configured

    raise FileNotFoundError("missing config at .pact/fitness.toml")


def run_check(root: pathlib.Path, check: dict) -> dict:
    timeout = int(check.get("timeout_seconds", 120))
    enabled = check.get("enabled", True)

    if not enabled:
        return {
            "id": check["id"],
            "description": check["description"],
            "severity": check["severity"],
            "status": "skipped",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }

    try:
        completed = subprocess.run(
            check["command"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        status = "pass" if completed.returncode == 0 else "fail"
        return {
            "id": check["id"],
            "description": check["description"],
            "severity": check["severity"],
            "status": status,
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "id": check["id"],
            "description": check["description"],
            "severity": check["severity"],
            "status": "fail",
            "exit_code": None,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"timed out after {timeout}s",
        }
    except OSError as exc:
        return {
            "id": check["id"],
            "description": check["description"],
            "severity": check["severity"],
            "status": "fail",
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PACT architecture fitness functions")
    parser.add_argument("--root", help="repository root; defaults to this script's repository")
    parser.add_argument("--config", help="fitness TOML (legacy YAML remains readable)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require project fitness config instead of an example fallback",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate configuration without executing project checks",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    default_root = pathlib.Path(__file__).resolve().parents[2]
    root = pathlib.Path(args.root).expanduser().resolve() if args.root else default_root
    schema_path = root / ".pact" / "schema" / "fitness.schema.json"

    if not schema_path.exists():
        print(f"PACT fitness: missing schema at {schema_path}", file=sys.stderr)
        return 2

    try:
        config, config_path, config_format, configured = load_config(
            root, args.config, args.strict
        )
    except Exception as exc:
        print(f"PACT fitness: {exc}", file=sys.stderr)
        return 2

    errors = validate_instance(config, load_schema(schema_path))
    if errors:
        print("PACT fitness: invalid config", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    source = (
        config_path.relative_to(root).as_posix()
        if config_path.is_relative_to(root)
        else str(config_path)
    )

    if args.validate_only:
        summary = {
            "overall": "pass",
            "configured": configured,
            "config_source": source,
            "config_format": config_format,
            "check_count": len(config["checks"]),
            "blocking_failures": 0,
            "warnings": 0,
            "validated_only": True,
            "results": [],
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("PACT fitness: config valid")
            print(f"- source: {source} ({config_format})")
            print(f"- configured checks: {summary['check_count']}")
        return 0

    results = [run_check(root, check) for check in config["checks"]]
    blocking = [
        item for item in results
        if item["status"] == "fail" and item["severity"] == "error"
    ]
    warnings = [
        item for item in results
        if item["status"] == "fail" and item["severity"] == "warn"
    ]

    summary = {
        "overall": "fail" if blocking else ("warn" if warnings else "pass"),
        "configured": configured,
        "config_source": source,
        "config_format": config_format,
        "check_count": len(results),
        "blocking_failures": len(blocking),
        "warnings": len(warnings),
        "validated_only": False,
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"PACT fitness: {summary['overall']}")
        if not configured:
            print(f"Using example fitness config: {source}")
        if not results:
            print("No architecture fitness functions configured.")
        for item in results:
            print(
                f"- [{item['status'].upper()}] {item['id']} "
                f"({item['severity']}): {item['description']}"
            )
            if item["status"] == "fail":
                if item["stdout"]:
                    print(f"  stdout: {item['stdout']}")
                if item["stderr"]:
                    print(f"  stderr: {item['stderr']}")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
