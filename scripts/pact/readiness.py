#!/usr/bin/env python3
"""Report explicit PACT adoption readiness."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

from formats import load_legacy_yaml, load_toml
from schema_validate import load_schema, validate_instance


REVIEW_KEYS = [
    "agent_bootstrap",
    "vocabulary",
    "product_truth",
    "architecture",
    "truth_ownership",
    "owner_profile",
    "verification",
    "known_drift",
]


def doctor_state(root: pathlib.Path) -> tuple[bool, str]:
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "pact" / "doctor.py"),
            "--strict",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, (result.stdout + result.stderr).strip()

    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "doctor output was not valid JSON"

    return report.get("overall") == "pass", report.get("overall", "unknown")


def load_baseline(root: pathlib.Path) -> tuple[dict | None, pathlib.Path | None, str | None]:
    toml_path = root / ".pact" / "baseline.toml"
    if toml_path.exists():
        return load_toml(toml_path), toml_path, "toml"

    legacy_path = root / ".pact" / "baseline.yaml"
    if legacy_path.exists():
        return load_legacy_yaml(legacy_path), legacy_path, "legacy-yaml"

    return None, None, None


def derive_stage(foundation_valid: bool, reviews: dict | None) -> str:
    if not foundation_valid or reviews is None:
        return "scaffolded"

    complete = [reviews.get(key) != "pending" for key in REVIEW_KEYS]

    if all(complete):
        return "pact-ready"

    if any(complete):
        return "baseline-in-progress"

    return "foundation-valid"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report PACT adoption readiness")
    parser.add_argument("--root", help="repository root; defaults to this script's repository")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return nonzero unless the project is PACT-ready",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    default_root = pathlib.Path(__file__).resolve().parents[2]
    root = pathlib.Path(args.root).expanduser().resolve() if args.root else default_root

    schema_path = root / ".pact" / "schema" / "baseline.schema.json"
    foundation_valid, foundation_detail = doctor_state(root)

    baseline = None
    baseline_path = None
    baseline_format = None
    baseline_errors: list[str] = []

    try:
        baseline, baseline_path, baseline_format = load_baseline(root)
        if baseline is not None:
            if baseline_format == "legacy-yaml":
                reviews = baseline.setdefault("reviews", {})
                reviews.setdefault("agent_bootstrap", "pending")

            if not schema_path.exists():
                baseline_errors.append(f"missing baseline schema at {schema_path}")
            else:
                baseline_errors.extend(validate_instance(baseline, load_schema(schema_path)))
    except Exception as exc:
        baseline_errors.append(str(exc))

    reviews = baseline.get("reviews") if baseline and not baseline_errors else None
    stage = derive_stage(foundation_valid, reviews)

    pending = [
        key for key in REVIEW_KEYS
        if reviews is not None and reviews.get(key) == "pending"
    ]

    result = {
        "stage": stage,
        "foundation_valid": foundation_valid,
        "foundation_detail": foundation_detail,
        "baseline_present": baseline_path is not None,
        "baseline_source": (
            baseline_path.relative_to(root).as_posix()
            if baseline_path is not None
            else None
        ),
        "baseline_format": baseline_format,
        "baseline_valid": baseline is not None and not baseline_errors,
        "reviews": reviews or {},
        "pending_reviews": pending,
        "errors": baseline_errors,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT readiness: {stage}")
        print(f"- foundation valid: {foundation_valid}")
        print(f"- baseline present: {result['baseline_present']}")
        print(f"- baseline valid: {result['baseline_valid']}")
        if baseline_format:
            print(f"- baseline format: {baseline_format}")
        if pending:
            print("Pending baseline reviews:")
            for key in pending:
                print(f"- {key}")
        if baseline_errors:
            print("Baseline errors:")
            for error in baseline_errors:
                print(f"- {error}")

    if baseline_errors:
        return 2
    if args.require_ready and stage != "pact-ready":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
