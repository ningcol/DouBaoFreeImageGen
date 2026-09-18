#!/usr/bin/env python3
"""Stable command dispatcher for PACT runtime tools."""

from __future__ import annotations

import pathlib
import subprocess
import sys

if sys.version_info < (3, 11):
    print("PACT 0.3 requires Python 3.11+.", file=sys.stderr)
    raise SystemExit(2)

HERE = pathlib.Path(__file__).resolve().parent

COMMANDS = {
    # Recommended agent-facing surface.
    "status": "status.py",
    "inspect": "inspect_project.py",
    "task": "task.py",

    # Setup / maintenance.
    "init": "init.py",
    "upgrade": "upgrade.py",
    "version": "version.py",

    # Advanced primitives.
    "check": "check.py",
    "schema-lint": "schema_lint.py",
    "workflow-lint": "workflow_lint.py",
    "doctor": "doctor.py",
    "readiness": "readiness.py",
    "audit": "audit.py",
    "owner": "owner.py",
    "risk": "risk.py",
    "fitness": "fitness.py",
    "map": "map.py",
    "code-map": "code_map.py",
    "discover": "discover.py",
    "explain": "explain.py",
    "context": "context.py",
    "impact": "impact.py",
    "run": "run.py",
    "converge": "converge.py",
    "evidence": "evidence.py",
    "report": "report.py",
    "complete": "complete.py",
    "eval": "eval.py",
}

RECOMMENDED = [
    ("status", "project foundation/readiness/health summary"),
    ("inspect", "inspect a remembered feature/business behavior"),
    ("task prepare", "prepare risk-adaptive context for a task"),
    ("task finish", "validate an existing completion bundle"),
    ("task status", "show one prepared task"),
]

SETUP = [
    ("init", "safely adopt PACT"),
    ("upgrade", "transactionally upgrade PACT runtime"),
    ("version", "show runtime/install version"),
]


def help_text() -> str:
    recommended = "\n".join(f"  {name:<14} {desc}" for name, desc in RECOMMENDED)
    setup = "\n".join(f"  {name:<14} {desc}" for name, desc in SETUP)
    advanced_names = [
        name
        for name in COMMANDS
        if name not in {"status", "inspect", "task", "init", "upgrade", "version"}
    ]
    advanced = "  " + "  ".join(advanced_names)

    return f"""PACT Project AI Control Plane

Usage:
  python3 pact.py <command> [args...]

Recommended agent surface:
{recommended}

Setup / maintenance:
{setup}

Advanced primitives:
{advanced}

Use low-level primitives when the default task surface is insufficient.
PACT keeps the primitives stable so stronger agents can bypass unnecessary
orchestration without weakening truth/evidence requirements.
"""


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        print(help_text())
        return 0

    command = sys.argv[1]
    script = COMMANDS.get(command)
    if not script:
        print(f"Unknown PACT command: {command}", file=sys.stderr)
        print(help_text(), file=sys.stderr)
        return 2

    completed = subprocess.run(
        [sys.executable, str(HERE / script), *sys.argv[2:]]
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
