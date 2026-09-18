"""Task Contract validation and acceptance-coverage review."""

from __future__ import annotations

import pathlib

from schema_validate import load_schema, validate_instance


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / ".pact" / "schema" / "task-contract.schema.json"


def validate(contract: dict) -> list[str]:
    return validate_instance(contract, load_schema(SCHEMA))


def acceptance_review(
    contract: dict,
    evidence: dict,
    owner: dict,
) -> tuple[list[str], dict]:
    errors: list[str] = []
    criteria = contract.get("acceptance_criteria", [])
    criterion_ids: list[str] = []
    criterion_by_id: dict[str, dict] = {}
    seen: set[str] = set()

    for item in criteria:
        criterion_id = item.get("id")
        if criterion_id in seen:
            errors.append(f"duplicate acceptance criterion id {criterion_id!r}")
            continue
        seen.add(criterion_id)
        criterion_ids.append(criterion_id)
        criterion_by_id[criterion_id] = item

    if contract.get("task_id") != evidence.get("task_id"):
        errors.append(
            "task contract task_id does not match Evidence "
            f"({contract.get('task_id')!r} != {evidence.get('task_id')!r})"
        )
    if contract.get("task_id") != owner.get("task_id"):
        errors.append(
            "task contract task_id does not match Owner Report "
            f"({contract.get('task_id')!r} != {owner.get('task_id')!r})"
        )

    known = set(criterion_ids)
    passing_by_criterion = {criterion_id: [] for criterion_id in criterion_ids}

    for claim in evidence.get("claims", []):
        claim_id = claim.get("id")
        for criterion_id in claim.get("criteria", []):
            if criterion_id not in known:
                errors.append(
                    f"Evidence claim {claim_id!r} references unknown "
                    f"acceptance criterion {criterion_id!r}"
                )
                continue
            if claim.get("status") == "pass":
                passing_by_criterion[criterion_id].append(claim_id)

    owner_acceptance: dict[str, dict] = {}
    for item in owner.get("acceptance", []):
        criterion_id = item.get("criterion_id")
        if criterion_id in owner_acceptance:
            errors.append(
                f"Owner Report contains duplicate acceptance entry {criterion_id!r}"
            )
            continue
        owner_acceptance[criterion_id] = item

    evidence_verified: list[str] = []
    owner_report_covered: list[str] = []
    unverified: list[str] = []
    owner_report_missing: list[str] = []

    for criterion_id in criterion_ids:
        passing = passing_by_criterion[criterion_id]
        if not passing:
            unverified.append(criterion_id)
            errors.append(
                f"acceptance criterion {criterion_id} has no passing Evidence claim"
            )
            continue

        evidence_verified.append(criterion_id)
        owner_item = owner_acceptance.get(criterion_id)
        if owner_item is None:
            owner_report_missing.append(criterion_id)
            errors.append(
                f"acceptance criterion {criterion_id} is verified by Evidence "
                "but missing from Owner Report acceptance"
            )
            continue

        expected_summary = criterion_by_id[criterion_id].get("text")
        if owner_item.get("summary") != expected_summary:
            owner_report_missing.append(criterion_id)
            errors.append(
                f"Owner Report acceptance {criterion_id} summary does not match "
                "the Task Contract criterion"
            )
            continue

        owner_ids = set(owner_item.get("evidence_ids", []))
        if not any(claim_id in owner_ids for claim_id in passing):
            owner_report_missing.append(criterion_id)
            errors.append(
                f"Owner Report acceptance {criterion_id} does not cite "
                "passing Evidence for that criterion"
            )
            continue

        owner_report_covered.append(criterion_id)

    return errors, {
        "total": len(criterion_ids),
        "evidence_verified": len(evidence_verified),
        "owner_report_covered": len(owner_report_covered),
        "unverified": unverified,
        "owner_report_missing": owner_report_missing,
    }
