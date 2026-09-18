#!/usr/bin/env python3
"""Validate evidence/convergence bindings and render an owner-readable PACT report."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from evidence import provenance_review, readiness as evidence_readiness, validate as validate_evidence
from schema_validate import load_schema, validate_instance


ROOT = pathlib.Path(__file__).resolve().parents[2]
OWNER_SCHEMA = ROOT / ".pact" / "schema" / "owner-report.schema.json"
CONVERGENCE_SCHEMA = ROOT / ".pact" / "schema" / "convergence-report.schema.json"

BLOCKING_CONVERGENCE = {"needs-reconciliation", "needs-owner"}


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(data: dict, schema_path: pathlib.Path, label: str) -> list[str]:
    errors = validate_instance(data, load_schema(schema_path))
    return [f"{label}.{error}" for error in errors]


def convergence_outcome(report: dict) -> str:
    classes = [f.get("classification") for f in report.get("findings", [])]
    dispositions = {
        item.get("disposition")
        for item in report.get("coverage", [])
        if isinstance(item, dict)
    }
    if "owner-decision" in classes or "owner-decision" in dispositions:
        return "needs-owner"
    if any(c in {"missing", "partial", "contradicts"} for c in classes):
        return "needs-reconciliation"
    if "stale" in classes or "stale" in dispositions:
        return "nonblocking-drift"
    return "aligned"


def cross_validate(
    owner: dict,
    evidence: dict,
    convergence: dict,
    *,
    root: pathlib.Path = ROOT,
    validate_provenance: bool = True,
) -> list[str]:
    errors: list[str] = []

    task_ids = {
        "owner": owner.get("task_id"),
        "evidence": evidence.get("task_id"),
        "convergence": convergence.get("task_id"),
    }
    if len(set(task_ids.values())) != 1:
        errors.append(
            "task_id mismatch across owner/evidence/convergence: "
            + ", ".join(f"{key}={value!r}" for key, value in task_ids.items())
        )

    claims_by_id = {
        claim["id"]: claim
        for claim in evidence.get("claims", [])
    }

    for item in owner.get("verification", []):
        for evidence_id in item.get("evidence_ids", []):
            claim = claims_by_id.get(evidence_id)
            if claim is None:
                errors.append(
                    f"owner verification references unknown evidence id '{evidence_id}'"
                )
                continue
            if claim.get("status") != "pass":
                errors.append(
                    f"owner verification references non-passing evidence id "
                    f"'{evidence_id}' (status={claim.get('status')!r})"
                )

    if validate_provenance:
        provenance_errors, policy_gaps, _ = provenance_review(evidence, root)
        errors.extend(f"evidence provenance: {error}" for error in provenance_errors)
    else:
        policy_gaps = []

    ready = evidence_readiness(evidence, policy_gaps)
    conv = convergence_outcome(convergence)

    if owner.get("status") == "completed":
        if ready != "ready":
            errors.append(
                f"owner status is completed but evidence readiness is '{ready}'"
            )
        if conv in BLOCKING_CONVERGENCE:
            errors.append(
                f"owner status is completed but convergence outcome is '{conv}'"
            )

    if owner.get("status") == "needs-owner" and conv != "needs-owner":
        errors.append(
            "owner status is needs-owner but convergence has no owner-decision finding"
        )

    expected_consistency = {
        "aligned": "aligned",
        "nonblocking-drift": "nonblocking-drift",
        "needs-reconciliation": "needs-reconciliation",
        "needs-owner": "needs-owner",
    }[conv]

    if owner.get("consistency", {}).get("status") != expected_consistency:
        errors.append(
            "owner consistency status does not match convergence outcome "
            f"('{expected_consistency}')"
        )

    return errors


def render(owner: dict) -> None:
    status_label = {
        "completed": "Completed",
        "partial": "Partially completed",
        "blocked": "Blocked",
        "needs-owner": "Needs your decision",
    }[owner["status"]]

    print(status_label)
    print()
    print(owner["summary"])
    print()
    print("Before:")
    print(owner["before"])
    print()
    print("Now:")
    print(owner["after"])

    if owner["verification"]:
        print()
        print("Verified:")
        for item in owner["verification"]:
            print(f"- {item['claim']}")

    if owner.get("acceptance"):
        print()
        print("Acceptance:")
        for item in owner["acceptance"]:
            print(f"- {item['criterion_id']}: {item['summary']}")

    print()
    print("Project consistency:")
    print(owner["consistency"]["summary"])

    if owner["owner_decisions"]:
        print()
        print("Decision needed:")
        for decision in owner["owner_decisions"]:
            print(decision["question"])
            for option in decision["options"]:
                print(f"- {option['label']}: {option['consequence']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a PACT owner report")
    parser.add_argument("owner_report")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--convergence", required=True)
    parser.add_argument(
        "--root",
        help="repository root used to resolve Evidence provenance refs",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = pathlib.Path(args.root).expanduser().resolve() if args.root else ROOT

    paths = [
        pathlib.Path(args.owner_report),
        pathlib.Path(args.evidence),
        pathlib.Path(args.convergence),
    ]
    paths = [p if p.is_absolute() else root / p for p in paths]

    try:
        owner, evidence, convergence = [load(p) for p in paths]
    except Exception as exc:
        print(f"PACT report: cannot read inputs: {exc}", file=sys.stderr)
        return 2

    errors = []
    errors.extend(validate(owner, OWNER_SCHEMA, "owner"))
    errors.extend(
        f"evidence.{error}" for error in validate_evidence(evidence)
    )
    errors.extend(validate(convergence, CONVERGENCE_SCHEMA, "convergence"))

    if not errors:
        errors.extend(cross_validate(owner, evidence, convergence, root=root))

    if errors:
        print("PACT report: invalid or unsupported owner claims", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(owner, ensure_ascii=False, indent=2))
    else:
        render(owner)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
