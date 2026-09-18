#!/usr/bin/env python3
"""Prepare a combined project explanation/code evidence packet."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "scripts" / "pact"


def run_json(command: list[str], *, allow_empty: bool = False) -> dict:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "PACT child command failed")
    if not result.stdout.strip():
        if allow_empty:
            return {}
        raise RuntimeError("PACT child command returned no JSON")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a remembered project feature/business behavior"
    )
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=12)
    code_group = parser.add_mutually_exclusive_group()
    code_group.add_argument("--code", dest="code", action="store_true")
    code_group.add_argument("--no-code", dest="code", action="store_false")
    parser.set_defaults(code=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        explanation = run_json([
            sys.executable,
            str(RUNTIME / "explain.py"),
            args.query,
            "--limit",
            str(args.limit),
            "--json",
        ])

        discover_command = [
            sys.executable,
            str(RUNTIME / "discover.py"),
            args.query,
            "--limit",
            str(args.limit),
            "--json",
        ]
        if args.code:
            discover_command.extend(["--code", "--code-limit", str(args.limit)])
        discovery = run_json(discover_command, allow_empty=True)
    except Exception as exc:
        print(f"PACT inspect: {exc}", file=sys.stderr)
        return 2

    result = {
        "query": args.query,
        "explanation": explanation,
        "discovery": discovery,
        "next_steps": explanation.get("followup", []),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT inspect: {args.query}")
        print(f"- product truth: {len(explanation.get('product_truth', []))}")
        print(f"- architecture: {len(explanation.get('architecture', []))}")
        print(f"- decisions: {len(explanation.get('decisions', []))}")
        print(f"- changes: {len(explanation.get('changes', []))}")
        print(f"- drift: {len(explanation.get('drift', []))}")
        print(f"- code matches: {discovery.get('code_result_count', 0)}")
        if explanation.get("gaps"):
            print("Gaps:")
            for gap in explanation["gaps"]:
                print(f"- {gap}")
        if result["next_steps"]:
            print("Suggested evidence expansion:")
            for step in result["next_steps"]:
                print(f"- {step}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
