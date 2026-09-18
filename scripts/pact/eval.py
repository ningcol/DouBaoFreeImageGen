#!/usr/bin/env python3
"""Validate/summarize pilot records and derive machine-observed task metrics."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from collections import defaultdict

from schema_validate import load_schema, validate_instance
from task_contract import acceptance_review


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / ".pact" / "schema" / "pilot-evaluation.schema.json"
OBSERVATION_SCHEMA = ROOT / ".pact" / "schema" / "task-observation.schema.json"


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional(path: pathlib.Path) -> dict | None:
    if not path.is_file():
        return None
    return load(path)


def read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []

    items: list[dict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSONL at {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError(
                f"invalid JSONL object at {path}:{line_number}"
            )
        items.append(value)
    return items


def validate(record: dict) -> list[str]:
    return validate_instance(record, load_schema(SCHEMA))


def validate_observation(record: dict) -> list[str]:
    return validate_instance(record, load_schema(OBSERVATION_SCHEMA))


def aggregate(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["mode"]].append(record)

    summary = {}

    for mode, items in sorted(groups.items()):
        count = len(items)
        tech_escalations = sum(
            item["owner_interactions"]["technical_escalations"]
            for item in items
        )
        product_decisions = sum(
            item["owner_interactions"]["product_decisions"]
            for item in items
        )
        clarifications = sum(
            item["owner_interactions"]["clarification_rounds"]
            for item in items
        )
        clear_count = sum(
            item["owner_interactions"]["comprehension"] == "clear"
            for item in items
        )
        done_blocked = sum(
            item["completion_integrity"]["unsupported_done_claims_blocked"]
            for item in items
        )
        evidence_gaps = sum(
            item["completion_integrity"]["evidence_gaps_found"]
            for item in items
        )
        convergence = sum(
            item["completion_integrity"]["convergence_findings"]
            for item in items
        )
        explain_used = [
            item["project_memory"]["explain_outcome"]
            for item in items
            if item["project_memory"]["explain_used"]
        ]
        explain_resolved = sum(value == "resolved" for value in explain_used)
        overload = sum(
            item["context_quality"]["overload_observed"]
            for item in items
        )
        overhead = [
            float(item["pact_overhead_minutes"])
            for item in items
            if item.get("pact_overhead_minutes") is not None
        ]

        summary[mode] = {
            "task_count": count,
            "completed": sum(item["outcome"] == "completed" for item in items),
            "product_decisions": product_decisions,
            "technical_escalations": tech_escalations,
            "clarification_rounds": clarifications,
            "owner_clear_rate": clear_count / count if count else None,
            "unsupported_done_claims_blocked": done_blocked,
            "evidence_gaps_found": evidence_gaps,
            "convergence_findings": convergence,
            "explain_uses": len(explain_used),
            "explain_resolved_rate": (
                explain_resolved / len(explain_used)
                if explain_used
                else None
            ),
            "context_overload_tasks": overload,
            "mean_knowledge_artifacts": statistics.fmean(
                item["context_quality"]["knowledge_artifacts"]
                for item in items
            ) if items else None,
            "mean_code_artifacts": statistics.fmean(
                item["context_quality"]["code_artifacts"]
                for item in items
            ) if items else None,
            "overhead_minutes_observed_count": len(overhead),
            "mean_pact_overhead_minutes": (
                statistics.fmean(overhead) if overhead else None
            ),
        }

    return {
        "record_count": len(records),
        "by_mode": summary,
        "interpretation_note": (
            "Directional pilot evidence only. Compare similar task/risk groups and do not collapse dimensions into one score."
        ),
    }


def blocker_count(
    attempts: list[dict],
    code: str,
    *legacy_needles: str,
) -> int:
    count = 0
    for attempt in attempts:
        blockers = attempt.get("blockers")
        if isinstance(blockers, list) and code in blockers:
            count += 1
            continue
        text = "\n".join(str(value) for value in attempt.get("errors", []))
        if any(needle in text for needle in legacy_needles):
            count += 1
    return count


def run_receipts(task_id: str, evidence: dict | None) -> list[dict]:
    paths: set[pathlib.Path] = set()
    root = ROOT / ".pact" / "runs" / task_id
    if root.is_dir():
        paths.update(root.rglob("*.json"))

    if evidence:
        for claim in evidence.get("claims", []):
            for item in claim.get("evidence", []):
                if item.get("provenance") != "pact-run":
                    continue
                ref = item.get("ref")
                if not isinstance(ref, str) or not ref:
                    continue
                path = pathlib.Path(ref).expanduser()
                paths.add(path if path.is_absolute() else ROOT / path)

    receipts: list[dict] = []
    seen: set[pathlib.Path] = set()
    for path in sorted(paths):
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        item = load_optional(resolved)
        if item and item.get("task_id") == task_id and "status" in item:
            receipts.append(item)
    return receipts


def derive_task(task_id: str) -> dict:
    task_dir = ROOT / ".pact" / "tasks" / task_id
    manifest = load_optional(task_dir / "task.json")
    if manifest is None:
        raise FileNotFoundError(f"task manifest not found for {task_id}")

    contract_path = manifest.get("contract")
    contract = (
        load_optional(ROOT / contract_path)
        if isinstance(contract_path, str)
        else None
    )
    context_path = manifest.get("context")
    context = (
        load_optional(ROOT / context_path)
        if isinstance(context_path, str)
        else None
    )

    bundle = ROOT / manifest.get(
        "completion_bundle",
        f".pact/completions/{task_id}",
    )
    evidence = load_optional(bundle / "evidence.json")
    convergence = load_optional(bundle / "convergence.json")
    owner = load_optional(bundle / "owner-report.json")

    criteria = contract.get("acceptance_criteria", []) if contract else []
    acceptance = {
        "total": len(criteria),
        "outcomes": sum(item.get("kind") == "outcome" for item in criteria),
        "constraints": sum(item.get("kind") == "constraint" for item in criteria),
        "evidence_verified": 0,
        "owner_report_covered": 0,
        "unverified": [item.get("id") for item in criteria],
        "owner_report_missing": [],
    }
    if contract and evidence and owner:
        _, coverage = acceptance_review(contract, evidence, owner)
        acceptance = {
            **coverage,
            "outcomes": sum(item.get("kind") == "outcome" for item in criteria),
            "constraints": sum(item.get("kind") == "constraint" for item in criteria),
        }

    attempts = read_jsonl(task_dir / "completion-attempts.jsonl")
    receipts = run_receipts(task_id, evidence)

    claims = evidence.get("claims", []) if evidence else []
    findings = convergence.get("findings", []) if convergence else []

    observation = {
        "version": 1,
        "task_id": task_id,
        "task_status": manifest.get("status", "unknown"),
        "risk_level": manifest.get("risk_level", "medium"),
        "acceptance": acceptance,
        "context": {
            "knowledge_artifacts": len(context.get("artifacts", [])) if context else 0,
            "code_artifacts": len(context.get("code_artifacts", [])) if context else 0,
            "known_unknowns": len(context.get("known_unknowns", [])) if context else 0,
        },
        "runs": {
            "total": len(receipts),
            "passed": sum(item.get("status") == "pass" for item in receipts),
            "failed": sum(item.get("status") == "fail" for item in receipts),
            "workspace_changed": sum(
                bool(item.get("workspace_changed")) for item in receipts
            ),
        },
        "completion": {
            "attempts": len(attempts),
            "failed_attempts": sum(not bool(item.get("complete")) for item in attempts),
            "stale_workspace_blocks": blocker_count(
                attempts,
                "stale-workspace",
                "stale pact-run receipt",
                "verified workspace",
            ),
            "stale_contract_blocks": blocker_count(
                attempts,
                "stale-task-contract",
                "task_contract_sha256",
            ),
            "acceptance_gap_blocks": blocker_count(
                attempts,
                "acceptance-gap",
                "acceptance criterion",
                "Owner Report acceptance",
            ),
            "convergence_coverage_blocks": blocker_count(
                attempts,
                "convergence-coverage",
                "convergence coverage:",
            ),
            "ci_requirement_blocks": blocker_count(
                attempts,
                "ci-required",
                "CI-backed Evidence",
            ),
            "final_complete": manifest.get("status") == "completed",
        },
        "evidence": {
            "claims": len(claims),
            "passed": sum(item.get("status") == "pass" for item in claims),
            "failed": sum(item.get("status") == "fail" for item in claims),
            "unverified": sum(item.get("status") == "unverified" for item in claims),
        },
        "convergence": {
            "findings": len(findings),
            "owner_decisions": sum(
                item.get("classification") == "owner-decision"
                for item in findings
            ),
        },
        "owner_status": owner.get("status") if owner else None,
        "human_required": [
            "owner_interactions.product_decisions",
            "owner_interactions.technical_escalations",
            "owner_interactions.clarification_rounds",
            "owner_interactions.comprehension",
            "context_quality.overload_observed",
            "pact_overhead_minutes",
        ],
    }

    errors = validate_observation(observation)
    if errors:
        raise ValueError("invalid derived observation: " + "; ".join(errors))

    return observation


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate/summarize PACT pilot records or derive machine task observations"
    )
    parser.add_argument("records", nargs="*")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--task",
        help="derive machine-observed metrics from one prepared PACT task",
    )
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.task:
        if args.records or args.summary:
            parser.error("--task cannot be combined with record paths or --summary")
        try:
            result = derive_task(args.task)
        except Exception as exc:
            print(f"PACT eval: cannot derive task observation: {exc}", file=sys.stderr)
            return 2

        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            path = pathlib.Path(args.output)
            if not path.is_absolute():
                path = ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
            if not args.json:
                print(f"PACT eval observation: {path}")
        if args.json or not args.output:
            print(rendered, end="")
        return 0

    if not args.records:
        parser.error("provide evaluation record(s) or --task TASK-ID")

    records = []
    failures = []

    for raw in args.records:
        path = pathlib.Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        try:
            record = load(path)
        except Exception as exc:
            failures.append(f"{raw}: cannot read record: {exc}")
            continue

        errors = validate(record)
        if errors:
            failures.extend(f"{raw}: {error}" for error in errors)
            continue

        records.append(record)

    if failures:
        print("PACT eval: invalid record(s)", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 2

    if args.summary:
        result = aggregate(records)
    else:
        result = {
            "valid": True,
            "record_count": len(records),
            "task_ids": [record["task_id"] for record in records],
        }

    if args.json or args.summary:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT eval: {len(records)} valid record(s)")
        for record in records:
            print(f"- {record['task_id']} ({record['mode']}, {record['risk_level']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
