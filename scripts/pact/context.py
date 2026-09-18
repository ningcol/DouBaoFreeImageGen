#!/usr/bin/env python3
"""Build a risk-adaptive candidate PACT Task Context Envelope."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

from risk import profile
from schema_validate import load_schema, validate_instance


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / ".pact" / "schema" / "context-envelope.schema.json"


def run_discovery(
    query: str,
    knowledge_limit: int,
    *,
    code: bool,
    code_limit: int,
) -> dict:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "pact" / "discover.py"),
        query,
        "--limit",
        str(knowledge_limit),
        "--json",
    ]
    if code:
        command.extend([
            "--code",
            "--code-limit",
            str(code_limit),
        ])

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "discovery failed")
    if not result.stdout.strip():
        return {
            "query": query,
            "result_count": 0,
            "results": [],
            "code_result_count": 0,
            "code_results": [],
        }
    return json.loads(result.stdout)


def validate(envelope: dict) -> list[str]:
    return validate_instance(envelope, load_schema(SCHEMA))


def artifact_sha256(relative: str) -> str | None:
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a candidate PACT task context")
    parser.add_argument("task")
    parser.add_argument("--goal")
    parser.add_argument("--success", required=True, help="observable success condition")
    parser.add_argument("--risk", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--query", help="discovery query; defaults to task")
    parser.add_argument(
        "--limit",
        type=int,
        help="override risk-profile knowledge artifact limit",
    )
    parser.add_argument(
        "--code-limit",
        type=int,
        help="override risk-profile code artifact limit",
    )
    code_group = parser.add_mutually_exclusive_group()
    code_group.add_argument(
        "--code",
        dest="code",
        action="store_true",
        help="force code-aware context",
    )
    code_group.add_argument(
        "--no-code",
        dest="code",
        action="store_false",
        help="disable code-aware context even if the risk profile normally enables it",
    )
    parser.set_defaults(code=None)
    parser.add_argument("--output")
    args = parser.parse_args()

    goal = args.goal or args.task
    query = args.query or args.task
    risk = profile(args.risk)

    knowledge_limit = max(args.limit or risk["knowledge_limit"], 1)
    code_limit = max(args.code_limit or risk["code_limit"], 1)
    code_enabled = (
        risk["code_context_default"]
        if args.code is None
        else bool(args.code)
    )

    try:
        discovery = run_discovery(
            query,
            knowledge_limit,
            code=code_enabled,
            code_limit=code_limit,
        )
    except Exception as exc:
        print(f"PACT context: discovery failed: {exc}", file=sys.stderr)
        return 2

    results = discovery.get("results", [])
    domains = sorted({
        domain
        for result in results
        for domain in result.get("domains", [])
    })

    rules = sorted({
        result["id"] or result["path"]
        for result in results
        if result.get("artifact_type") == "rule"
        and result.get("status") == "confirmed"
    })
    decisions = sorted({
        result["id"] or result["path"]
        for result in results
        if result.get("artifact_type") == "decision"
        and result.get("status") == "implemented"
    })
    verification = sorted({
        target
        for result in results
        for target in result.get("verification", [])
    })
    architecture = [
        result
        for result in results
        if result.get("artifact_type") == "architecture"
        or str(result.get("path", "")).startswith("docs/architecture/")
    ]

    code_results = discovery.get("code_results", [])

    unknowns: list[str] = []
    if not results:
        unknowns.append(
            "Project Discovery found no matching knowledge artifact; expand search semantically."
        )
    if not rules:
        unknowns.append(
            "No confirmed Product Rule was discovered; candidate rules must not be treated as normative truth."
        )
    if code_enabled and not code_results:
        unknowns.append(
            "Code-aware discovery found no matching code artifact; expand with project-specific code analysis if needed."
        )

    if args.risk == "high":
        if not architecture:
            unknowns.append(
                "High-risk task: no matching current Architecture artifact was discovered; inspect architecture/contracts manually."
            )
        if not decisions:
            unknowns.append(
                "High-risk task: no implemented Decision Record was discovered; inspect Decision/Git history when rationale matters."
            )
        unknowns.append(
            "High-risk task: inspect relevant public contracts/schema and Git history when the change can affect them."
        )

    envelope = {
        "version": 1,
        "status": "candidate",
        "task": args.task,
        "goal": goal,
        "observable_success": args.success,
        "risk_level": args.risk,
        "risk_policy": {
            "knowledge_limit": knowledge_limit,
            "code_context": code_enabled,
            "code_limit": code_limit,
            "completion": risk["completion"],
        },
        "discovery_query": query,
        "domains": domains,
        "artifacts": [
            {
                "path": item["path"],
                "id": item.get("id"),
                "artifact_type": item["artifact_type"],
                "title": item["title"],
                "score": item["score"],
                "reasons": item.get("reasons", []),
                "sha256": artifact_sha256(item["path"]),
            }
            for item in results
        ],
        "code_artifacts": [
            {
                "path": item["path"],
                "language": item["language"],
                "is_test": item["is_test"],
                "symbols": item.get("symbols", []),
                "score": item["score"],
                "reasons": item.get("reasons", []),
                "relation": item.get("relation", "direct-match"),
                "confidence": item.get("confidence", "heuristic"),
            }
            for item in code_results
        ],
        "applicable_rules": rules,
        "decisions": decisions,
        "verification_targets": verification,
        "known_unknowns": unknowns,
    }

    errors = validate(envelope)
    if errors:
        print("PACT context: generated invalid envelope", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    rendered = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        path = pathlib.Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"PACT context: candidate envelope -> {path}")
    else:
        print(rendered, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
