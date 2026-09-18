#!/usr/bin/env python3
"""High-level PACT task lifecycle helpers.

This command composes existing PACT primitives. It does not replace the
low-level commands or invent semantic Evidence/Convergence on the Agent's behalf.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

from task_contract import validate as validate_contract


ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "scripts" / "pact"
TASK_ROOT = ROOT / ".pact" / "tasks"
COMPLETION_ROOT = ROOT / ".pact" / "completions"


def generated_task_id(task: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = hashlib.sha256(task.encode("utf-8")).hexdigest()[:8].upper()
    return f"TASK-{stamp}-{suffix}"


def write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def completion_blockers(errors: list[str]) -> list[str]:
    text = "\n".join(str(value) for value in errors)
    blockers: list[str] = []
    checks = [
        ("stale-workspace", ("stale pact-run receipt", "verified workspace")),
        ("stale-task-contract", ("task_contract_sha256",)),
        ("acceptance-gap", ("acceptance criterion", "Owner Report acceptance")),
        ("convergence-coverage", ("convergence coverage:",)),
        ("ci-required", ("CI-backed Evidence",)),
    ]
    for code, needles in checks:
        if any(needle in text for needle in needles):
            blockers.append(code)
    return blockers


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def prepare(args) -> int:
    task_id = args.task_id or generated_task_id(args.task)
    task_dir = TASK_ROOT / task_id
    if task_dir.exists() and not args.force:
        print(
            f"PACT task prepare: task already exists: {task_dir} "
            "(use --force only to rebuild derived preparation files)",
            file=sys.stderr,
        )
        return 2
    task_dir.mkdir(parents=True, exist_ok=True)

    acceptance_items = [
        ("outcome", text)
        for text in [args.success, *args.acceptance]
    ] + [
        ("constraint", text)
        for text in args.constraint
    ]
    contract = {
        "version": 1,
        "task_id": task_id,
        "intent": args.goal or args.task,
        "acceptance_criteria": [
            {"id": f"AC-{index}", "kind": kind, "text": text}
            for index, (kind, text) in enumerate(acceptance_items, start=1)
        ],
    }
    contract_errors = validate_contract(contract)
    if contract_errors:
        print("PACT task prepare: generated invalid Task Contract", file=sys.stderr)
        for error in contract_errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    contract_path = task_dir / "contract.json"
    write_json(contract_path, contract)
    contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    context_path = task_dir / "context.json"
    context_cmd = [
        sys.executable,
        str(RUNTIME / "context.py"),
        args.task,
        "--success",
        "; ".join(text for _, text in acceptance_items),
        "--risk",
        args.risk,
        "--output",
        str(context_path),
    ]
    if args.goal:
        context_cmd.extend(["--goal", args.goal])
    if args.query:
        context_cmd.extend(["--query", args.query])
    if args.code is True:
        context_cmd.append("--code")
    elif args.code is False:
        context_cmd.append("--no-code")

    context_result = run(context_cmd)
    if context_result.returncode != 0:
        print(context_result.stdout, end="")
        print(context_result.stderr, end="", file=sys.stderr)
        return context_result.returncode

    context_sha256 = hashlib.sha256(context_path.read_bytes()).hexdigest()

    impact_path = None
    impact_state = "deferred"
    impact_cmd = None
    if args.files or args.base:
        impact_path = task_dir / "impact.json"
        impact_cmd = [
            sys.executable,
            str(RUNTIME / "impact.py"),
            "--risk",
            args.risk,
            "--output",
            str(impact_path),
        ]
        if args.files:
            impact_cmd.extend(["--files", *args.files])
        else:
            impact_cmd.extend(["--base", args.base, "--head", args.head])
        if args.code is True:
            impact_cmd.append("--code")
        elif args.code is False:
            impact_cmd.append("--no-code")

        impact_result = run(impact_cmd)
        if impact_result.returncode != 0:
            print(impact_result.stdout, end="")
            print(impact_result.stderr, end="", file=sys.stderr)
            return impact_result.returncode
        impact_state = "prepared"

    manifest = {
        "version": 1,
        "task_id": task_id,
        "status": "prepared",
        "task": args.task,
        "goal": args.goal or args.task,
        "observable_success": args.success,
        "risk_level": args.risk,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract": contract_path.relative_to(ROOT).as_posix(),
        "contract_sha256": contract_sha256,
        "acceptance_criteria_count": len(contract["acceptance_criteria"]),
        "context": context_path.relative_to(ROOT).as_posix(),
        "context_sha256": context_sha256,
        "impact": (
            impact_path.relative_to(ROOT).as_posix()
            if impact_path is not None
            else None
        ),
        "impact_state": impact_state,
        "completion_bundle": (
            COMPLETION_ROOT / task_id
        ).relative_to(ROOT).as_posix(),
    }
    manifest_path = task_dir / "task.json"
    write_json(manifest_path, manifest)

    result = {
        **manifest,
        "task_dir": task_dir.relative_to(ROOT).as_posix(),
        "next": (
            "Implement and verify every Task Contract acceptance criterion. "
            "Evidence claims that prove acceptance must list the relevant "
            "criteria IDs. Convergence must bind the prepared context_sha256 "
            "and explicitly cover every context.artifacts entry. Create "
            "evidence.json, convergence.json, and owner-report.json in the "
            "completion bundle, then run "
            f"'pact task finish {task_id}'."
        ),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT task prepared: {task_id}")
        print(f"- risk: {args.risk}")
        print(f"- contract: {manifest['contract']} ({manifest['acceptance_criteria_count']} acceptance criteria)")
        print(f"- context: {manifest['context']} (sha256={manifest['context_sha256'][:12]}...)")
        print(f"- impact: {impact_state}")
        if impact_state == "deferred":
            print(
                "- impact note: no changed-file/base input was supplied; run "
                "low-level impact later or rebuild preparation with --files/--base."
            )
        print(f"- completion bundle: {manifest['completion_bundle']}")
        print("- next: " + result["next"])

    return 0


def finish(args) -> int:
    task_dir = TASK_ROOT / args.task_id
    manifest_path = task_dir / "task.json"
    if not manifest_path.is_file():
        print(
            f"PACT task finish: task was not prepared: {args.task_id}. "
            "Use 'pact task prepare' first, or use the low-level 'pact complete' "
            "primitive for a legacy/unmanaged completion bundle.",
            file=sys.stderr,
        )
        return 2

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"PACT task finish: invalid task manifest: {manifest_path}", file=sys.stderr)
        return 2

    bundle = pathlib.Path(args.bundle) if args.bundle else COMPLETION_ROOT / args.task_id
    if not bundle.is_absolute():
        bundle = ROOT / bundle

    command = [
        sys.executable,
        str(RUNTIME / "complete.py"),
        str(bundle),
        "--root",
        str(ROOT),
        "--json",
    ]
    if args.require_ci:
        command.append("--require-ci")

    if manifest is not None and manifest.get("contract"):
        command.extend(["--contract", str(ROOT / manifest["contract"])])

    if (
        manifest is not None
        and manifest.get("context")
        and manifest.get("context_sha256")
    ):
        command.extend(["--context", str(ROOT / manifest["context"])])
        command.extend(["--context-sha256", manifest["context_sha256"]])

    completed = run(command)
    output = None
    if completed.stdout.strip():
        try:
            output = json.loads(completed.stdout)
        except json.JSONDecodeError:
            pass

    attempt = {
        "version": 1,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "returncode": int(completed.returncode),
        "result_available": output is not None,
        "complete": bool(output.get("complete")) if output is not None else False,
        "errors": output.get("errors", []) if output is not None else [],
        "blockers": completion_blockers(
            output.get("errors", []) if output is not None else []
        ),
        "policy_gaps": output.get("policy_gaps", []) if output is not None else [],
        "acceptance": output.get("acceptance") if output is not None else None,
    }
    append_jsonl(task_dir / "completion-attempts.jsonl", attempt)

    if completed.returncode == 0 and manifest is not None:
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        try:
            bundle_display = bundle.relative_to(ROOT).as_posix()
        except ValueError:
            bundle_display = str(bundle)
        manifest["completion_bundle"] = bundle_display
        write_json(manifest_path, manifest)

    if args.json and output is not None:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)

    return completed.returncode


def task_status(args) -> int:
    task_dir = TASK_ROOT / args.task_id
    manifest_path = task_dir / "task.json"
    if not manifest_path.is_file():
        print(f"PACT task status: unknown task {args.task_id}", file=sys.stderr)
        return 2

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"PACT task status: invalid task manifest: {exc}", file=sys.stderr)
        return 2

    bundle = COMPLETION_ROOT / args.task_id
    completion_files = {
        name: (bundle / filename).is_file()
        for name, filename in {
            "evidence": "evidence.json",
            "convergence": "convergence.json",
            "owner_report": "owner-report.json",
        }.items()
    }

    contract = None
    contract_path = manifest.get("contract")
    if contract_path:
        path = ROOT / contract_path
        if path.is_file():
            try:
                contract = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                contract = None

    result = {
        **manifest,
        "acceptance_criteria": (
            contract.get("acceptance_criteria", []) if contract else []
        ),
        "completion_files": completion_files,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT task {args.task_id}: {manifest.get('status')}")
        print(f"- risk: {manifest.get('risk_level')}")
        print(f"- acceptance criteria: {len(result['acceptance_criteria'])}")
        print(f"- context: {manifest.get('context')}")
        print(f"- impact: {manifest.get('impact_state')}")
        print(
            "- completion files: "
            + ", ".join(
                f"{name}={'yes' if present else 'no'}"
                for name, present in completion_files.items()
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PACT high-level task surface")
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="prepare risk-adaptive task context")
    prep.add_argument("task")
    prep.add_argument("--success", required=True)
    prep.add_argument(
        "--accept",
        dest="acceptance",
        action="append",
        default=[],
        help="additional observable acceptance criterion (repeatable)",
    )
    prep.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="task constraint that must be preserved (repeatable)",
    )
    prep.add_argument("--goal")
    prep.add_argument("--risk", choices=["low", "medium", "high"], default="medium")
    prep.add_argument("--query")
    prep.add_argument("--task-id")
    prep.add_argument("--files", nargs="+")
    prep.add_argument("--base")
    prep.add_argument("--head", default="HEAD")
    prep.add_argument("--force", action="store_true")
    code = prep.add_mutually_exclusive_group()
    code.add_argument("--code", dest="code", action="store_true")
    code.add_argument("--no-code", dest="code", action="store_false")
    prep.set_defaults(code=None)
    prep.add_argument("--json", action="store_true")

    finish_parser = sub.add_parser("finish", help="validate an existing task completion bundle")
    finish_parser.add_argument("task_id")
    finish_parser.add_argument("--bundle")
    finish_parser.add_argument("--require-ci", action="store_true")
    finish_parser.add_argument("--json", action="store_true")

    status_parser = sub.add_parser("status", help="show one prepared task")
    status_parser.add_argument("task_id")
    status_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "prepare":
        if args.files and args.base:
            parser.error("--files and --base are mutually exclusive")
        return prepare(args)
    if args.command == "finish":
        return finish(args)
    return task_status(args)


if __name__ == "__main__":
    raise SystemExit(main())
