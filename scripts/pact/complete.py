#!/usr/bin/env python3
"""Validate a complete PACT task completion bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

from evidence import (
    provenance_review,
    readiness as evidence_readiness,
    validate as validate_evidence,
)
from report import (
    CONVERGENCE_SCHEMA,
    OWNER_SCHEMA,
    convergence_outcome,
    cross_validate,
    validate as validate_report_part,
)
from task_contract import acceptance_review, validate as validate_contract


ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Evidence + Convergence + Owner Report as one completion gate"
    )
    parser.add_argument(
        "bundle",
        help="directory containing evidence.json, convergence.json, owner-report.json",
    )
    parser.add_argument(
        "--root",
        help="repository root used to resolve Evidence provenance refs",
    )
    parser.add_argument(
        "--require-ci",
        action="store_true",
        help="require at least one CI-backed Evidence claim for completion",
    )
    parser.add_argument(
        "--contract",
        help="optional Task Contract; when present every acceptance criterion must be verified and owner-visible",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = pathlib.Path(args.root).expanduser().resolve() if args.root else ROOT
    bundle = pathlib.Path(args.bundle).expanduser()
    if not bundle.is_absolute():
        bundle = root / bundle
    bundle = bundle.resolve()

    files = {
        "evidence": bundle / "evidence.json",
        "convergence": bundle / "convergence.json",
        "owner": bundle / "owner-report.json",
    }

    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        print(
            "PACT complete: missing bundle file(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    try:
        evidence = load(files["evidence"])
        convergence = load(files["convergence"])
        owner = load(files["owner"])
    except Exception as exc:
        print(f"PACT complete: cannot read bundle: {exc}", file=sys.stderr)
        return 2

    contract = None
    contract_path = None
    if args.contract:
        contract_path = pathlib.Path(args.contract).expanduser()
        if not contract_path.is_absolute():
            contract_path = root / contract_path
        try:
            contract = load(contract_path.resolve())
        except Exception as exc:
            print(f"PACT complete: cannot read Task Contract: {exc}", file=sys.stderr)
            return 2

    errors: list[str] = []
    errors.extend(f"evidence.{error}" for error in validate_evidence(evidence))
    errors.extend(validate_report_part(convergence, CONVERGENCE_SCHEMA, "convergence"))
    errors.extend(validate_report_part(owner, OWNER_SCHEMA, "owner"))
    contract_sha256 = None
    if contract is not None:
        errors.extend(
            f"contract.{error}" for error in validate_contract(contract)
        )
        if contract_path is not None:
            contract_sha256 = hashlib.sha256(
                contract_path.resolve().read_bytes()
            ).hexdigest()
        recorded_contract_sha = evidence.get("task_contract_sha256")
        if recorded_contract_sha != contract_sha256:
            errors.append(
                "evidence.task_contract_sha256 does not match current Task Contract "
                f"({recorded_contract_sha!r} != {contract_sha256!r})"
            )

    policy_gaps: list[str] = []
    provenance_stats = {
        "machine_backed_claims": 0,
        "workspace_bound_claims": 0,
        "ci_backed_claims": 0,
        "current_workspace": None,
    }
    acceptance_stats = None
    if not errors:
        provenance_errors, policy_gaps, provenance_stats = provenance_review(
            evidence, root
        )
        errors.extend(
            f"evidence provenance: {error}"
            for error in provenance_errors
        )
        errors.extend(
            cross_validate(
                owner,
                evidence,
                convergence,
                root=root,
                validate_provenance=False,
            )
        )
        if contract is not None:
            acceptance_errors, acceptance_stats = acceptance_review(
                contract,
                evidence,
                owner,
            )
            errors.extend(
                f"acceptance: {error}" for error in acceptance_errors
            )

    risk = evidence.get("risk_level")
    evidence_state = (
        evidence_readiness(evidence, policy_gaps)
        if not errors
        else "invalid"
    )
    convergence_state = (
        convergence_outcome(convergence)
        if not errors
        else "invalid"
    )

    if not errors and owner.get("status") != "completed":
        errors.append(
            f"completion bundle owner status must be 'completed', "
            f"found {owner.get('status')!r}"
        )

    if not errors and evidence_state != "ready":
        errors.append(
            f"completion bundle Evidence is not ready ({evidence_state})"
        )

    if not errors and convergence_state in {"needs-reconciliation", "needs-owner"}:
        errors.append(
            f"completion bundle Convergence is blocking ({convergence_state})"
        )

    if (
        not errors
        and args.require_ci
        and provenance_stats.get("ci_backed_claims", 0) == 0
    ):
        errors.append(
            "completion requires CI-backed Evidence but no claim is backed by "
            "a GitHub Actions pact-run receipt"
        )

    if not errors and risk == "high":
        if evidence.get("limitations"):
            errors.append(
                "high-risk completion cannot carry unresolved Evidence limitations"
            )
        if convergence_state != "aligned":
            errors.append(
                "high-risk completion requires fully aligned Convergence; "
                f"found {convergence_state}"
            )

    result = {
        "task_id": evidence.get("task_id"),
        "risk_level": risk,
        "evidence": evidence_state,
        "convergence": convergence_state,
        "owner_status": owner.get("status"),
        "complete": not errors,
        "errors": errors,
        "policy_gaps": policy_gaps,
        "machine_backed_claims": provenance_stats.get("machine_backed_claims", 0),
        "workspace_bound_claims": provenance_stats.get("workspace_bound_claims", 0),
        "ci_backed_claims": provenance_stats.get("ci_backed_claims", 0),
        "current_workspace": provenance_stats.get("current_workspace"),
        "acceptance": acceptance_stats,
        "contract": str(contract_path.resolve()) if contract_path else None,
        "contract_sha256": contract_sha256,
        "bundle": str(bundle),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT complete: {'PASS' if result['complete'] else 'FAIL'}")
        print(f"- task: {result['task_id']}")
        print(f"- risk: {risk}")
        print(f"- evidence: {evidence_state}")
        print(f"- convergence: {convergence_state}")
        print(f"- owner status: {owner.get('status')}")
        print(
            "- evidence backing: "
            f"machine={result['machine_backed_claims']}, "
            f"workspace-bound={result['workspace_bound_claims']}, "
            f"ci-backed={result['ci_backed_claims']}"
        )
        if acceptance_stats is not None:
            print(
                "- acceptance: "
                f"{acceptance_stats['owner_report_covered']}/"
                f"{acceptance_stats['total']} owner-visible and verified"
            )
        if policy_gaps:
            print("Policy gaps:")
            for gap in policy_gaps:
                print(f"- {gap}")
        if errors:
            print("Errors:")
            for error in errors:
                print(f"- {error}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
