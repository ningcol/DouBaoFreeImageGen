#!/usr/bin/env python3
"""High-level PACT project status for agents and owners."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "scripts" / "pact"


def run_json(script: str, *args: str) -> tuple[int, dict | None, str]:
    result = subprocess.run(
        [sys.executable, str(RUNTIME / script), *args, "--json"],
        capture_output=True,
        text=True,
    )
    data = None
    if result.stdout.strip():
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return result.returncode, data, (result.stdout + result.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Show high-level PACT project status")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require project-specific config/install provenance where supported",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    doctor_args = ["--strict"] if args.strict else []
    doctor_rc, doctor, doctor_raw = run_json("doctor.py", *doctor_args)
    readiness_rc, readiness, readiness_raw = run_json("readiness.py")
    audit_rc, audit, audit_raw = run_json("audit.py")

    result = {
        "foundation": {
            "state": doctor.get("overall") if doctor else "error",
            "detail": doctor,
        },
        "readiness": {
            "stage": readiness.get("stage") if readiness else "unknown",
            "pending_reviews": readiness.get("pending_reviews", []) if readiness else [],
            "detail": readiness,
        },
        "health": {
            "deterministic_check": audit.get("deterministic_check") if audit else "error",
            "active_changes": len(audit.get("active_changes", [])) if audit else None,
            "known_drift": len(audit.get("known_drift", [])) if audit else None,
            "semantic_review_targets": len(audit.get("semantic_review_targets", [])) if audit else None,
            "detail": audit,
        },
    }

    errors = []
    if doctor is None:
        errors.append(f"doctor failed: {doctor_raw}")
    if readiness is None:
        errors.append(f"readiness failed: {readiness_raw}")
    if audit is None:
        errors.append(f"audit failed: {audit_raw}")
    result["errors"] = errors

    blocking = (
        doctor_rc != 0
        or audit_rc != 0
        or bool(errors)
    )
    result["overall"] = "fail" if blocking else (
        "warn"
        if result["foundation"]["state"] == "warn"
        or result["readiness"]["stage"] != "pact-ready"
        or (result["health"]["known_drift"] or 0) > 0
        else "pass"
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT status: {result['overall']}")
        print(f"- foundation: {result['foundation']['state']}")
        print(f"- readiness: {result['readiness']['stage']}")
        pending = result["readiness"]["pending_reviews"]
        if pending:
            print("- pending baseline reviews: " + ", ".join(pending))
        print(f"- deterministic check: {result['health']['deterministic_check']}")
        print(f"- active changes: {result['health']['active_changes']}")
        print(f"- known drift: {result['health']['known_drift']}")
        if errors:
            print("Errors:")
            for error in errors:
                print(f"- {error}")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
