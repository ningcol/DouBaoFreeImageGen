#!/usr/bin/env python3
"""Validate and summarize a structured PACT Convergence Report."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from schema_validate import load_schema, validate_instance

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / ".pact" / "schema" / "convergence-report.schema.json"

BLOCKING_CLASSES = {"missing", "partial", "contradicts", "owner-decision"}


def load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(report: dict) -> list[str]:
    return validate_instance(report, load_schema(SCHEMA))


def outcome(report: dict) -> str:
    findings = report.get("findings", [])
    if any(f.get("classification") == "owner-decision" for f in findings):
        return "needs-owner"
    if any(f.get("classification") in BLOCKING_CLASSES for f in findings):
        return "needs-reconciliation"
    if any(f.get("classification") == "stale" for f in findings):
        return "converged-with-nonblocking-drift"
    return "converged"


def render(report: dict) -> None:
    print(f"PACT convergence: {outcome(report)}")
    print(f"Change: {report['change']}")
    print(f"Owner summary: {report['owner_summary']}")

    findings = report.get("findings", [])
    if not findings:
        print("Findings: none")
        return

    print("Findings:")
    for index, finding in enumerate(findings, start=1):
        print(
            f"{index}. [{finding['classification']}/{finding['severity']}] "
            f"{finding['subject']}"
        )
        print(f"   observed: {finding['observed']}")
        print(f"   expected: {finding['expected']}")
        print(f"   authority: {finding['authority']}")
        print(f"   action: {finding['recommended_action']}")
        if finding.get("owner_question"):
            print(f"   owner question: {finding['owner_question']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a PACT convergence report")
    parser.add_argument("report")
    parser.add_argument("--json", action="store_true", help="emit machine-readable outcome")
    args = parser.parse_args()

    path = pathlib.Path(args.report)
    if not path.is_absolute():
        path = ROOT / path

    try:
        report = load_json(path)
    except Exception as exc:
        print(f"PACT convergence: cannot read report: {exc}", file=sys.stderr)
        return 2

    errors = validate(report)
    if errors:
        print("PACT convergence: invalid report", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    result = {
        "outcome": outcome(report),
        "change": report["change"],
        "finding_count": len(report.get("findings", [])),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render(report)

    return 0 if result["outcome"] in {"converged", "converged-with-nonblocking-drift"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
