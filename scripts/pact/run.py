#!/usr/bin/env python3
"""Execute a command and write a PACT source-backed run receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

from schema_validate import load_schema, validate_instance
from security import redact_argv
from workspace import workspace_snapshot


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / ".pact" / "schema" / "run-receipt.schema.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ci_provenance() -> dict | None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None

    required = {
        "repository": "GITHUB_REPOSITORY",
        "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT",
        "job": "GITHUB_JOB",
        "workflow": "GITHUB_WORKFLOW",
        "sha": "GITHUB_SHA",
        "ref": "GITHUB_REF",
        "server_url": "GITHUB_SERVER_URL",
    }
    values = {}
    for key, env_name in required.items():
        value = os.environ.get(env_name)
        if not value:
            return None
        values[key] = value

    return {
        "provider": "github-actions",
        **values,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a command and create a PACT execution receipt"
    )
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cwd", help="command working directory; defaults to repository root")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="do not replay captured command stdout/stderr to the terminal",
    )
    parser.add_argument(
        "--redact-value",
        action="append",
        default=[],
        help="additional literal to redact from persisted argv; repeatable",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("PACT run: command is required after --", file=sys.stderr)
        return 2

    cwd = pathlib.Path(args.cwd).expanduser().resolve() if args.cwd else ROOT
    output = pathlib.Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    try:
        workspace_before = workspace_snapshot(cwd)
    except Exception as exc:
        print(f"PACT run: cannot fingerprint workspace before command: {exc}", file=sys.stderr)
        return 2

    started = now_iso()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            shell=False,
        )
    except OSError as exc:
        print(f"PACT run: cannot execute command: {exc}", file=sys.stderr)
        return 2
    finished = now_iso()

    if not args.quiet:
        if completed.stdout:
            sys.stdout.buffer.write(completed.stdout)
            sys.stdout.buffer.flush()
        if completed.stderr:
            sys.stderr.buffer.write(completed.stderr)
            sys.stderr.buffer.flush()

    try:
        workspace_after = workspace_snapshot(cwd)
    except Exception as exc:
        print(f"PACT run: cannot fingerprint workspace after command: {exc}", file=sys.stderr)
        return 2

    persisted_argv, redacted_count = redact_argv(
        command,
        extra_values=args.redact_value,
    )

    receipt = {
        "version": 2,
        "task_id": args.task_id,
        "argv": persisted_argv,
        "argv_redacted": True,
        "redacted_argument_count": redacted_count,
        "cwd": str(cwd),
        "started_at": started,
        "finished_at": finished,
        "exit_code": int(completed.returncode),
        "status": "pass" if completed.returncode == 0 else "fail",
        "stdout_sha256": sha256_bytes(completed.stdout),
        "stderr_sha256": sha256_bytes(completed.stderr),
        "git_head": workspace_after.get("git_head"),
        "git_dirty": workspace_after.get("dirty"),
        "workspace_before": workspace_before,
        "workspace_after": workspace_after,
        "workspace_changed": (
            workspace_before.get("sha256") != workspace_after.get("sha256")
        ),
        "ci": ci_provenance(),
    }

    errors = validate_instance(receipt, load_schema(SCHEMA))
    if errors:
        print("PACT run: generated invalid receipt", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PACT run receipt: {output}", file=sys.stderr)

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
