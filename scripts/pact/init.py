#!/usr/bin/env python3
"""Safely scaffold PACT into an existing repository.

Dry-run is the default. --apply writes only missing files and never overwrites.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

from distribution import (
    github_actions_entry,
    legacy_seed_target,
    manifest_record,
    runtime_version,
    sha256_file,
    source_manifest,
)

SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL_MANIFEST = pathlib.Path(".pact/install.json")

TARGET_AGENTS = """# Project Agent Guide

This repository uses PACT (Project AI Control Plane).

## Core rules

1. Preserve confirmed Product Truth.
2. Acquire sufficient context before changing behavior; do not read everything by default.
3. AI owns implementation decisions unless they change product meaning, permissions/policy, irreversible outcomes, material risk, or cost.
4. Distinguish what should be true from what the system currently does.
5. Verify observable outcomes before claiming completion.
6. Reconcile drift by authority; never make Product Truth follow code automatically.
7. Report owner-facing results in product/business language by default.

## Knowledge router

- Governance: `docs/governance/`
- Product Truth and vocabulary: `docs/product/`
- Current architecture: `docs/architecture/`
- Durable engineering rationale: `.agents/decisions/`
- Active/completed change intent: `docs/changes/`
- Drift: `docs/drift/`
- Reusable procedures: `.agents/skills/`
- Adoption readiness: `.pact/baseline.toml`

## Decision boundary

Do not ask the owner to choose ordinary implementation mechanisms.

Escalate only when a decision changes user-observable behavior, business/data meaning, permissions/policy, irreversible outcomes, or material risk/cost.

## Completion boundary

"Done" requires appropriate evidence and convergence, not only code changes or green tests.

## Baseline boundary

`pact init` creates structure; it does not certify project knowledge.

If `pact readiness` reports pending baseline reviews, treat those areas as potentially incomplete rather than inventing missing truth.

## Owner communication

Before owner-facing output, read the validated Owner Profile:

```bash
python scripts/pact/pact.py owner --json
```

Honor its language, technical depth, consequence-first translation, and progressive-disclosure preferences.
"""


def bootstrap_snippet() -> str:
    return """# PACT Agent Bootstrap

An existing `AGENTS.md` was detected, so PACT did not overwrite it.

Merge these concepts into the existing project agent guide:

- preserve confirmed Product Truth;
- distinguish normative truth from current implementation behavior;
- retrieve sufficient task context from Product, Architecture, Decisions, and Changes;
- let AI decide ordinary technical implementation;
- escalate only product/risk decisions;
- require evidence and convergence before claiming completion;
- consult `.pact/baseline.toml` and do not invent truth for pending baseline areas;
- communicate owner-facing results using the project Owner Profile in `.pact/config.toml`;
- use product/business consequences before unnecessary implementation detail.

Suggested knowledge router:

- Governance: `docs/governance/`
- Product Truth: `docs/product/`
- Architecture: `docs/architecture/`
- Decisions: `.agents/decisions/`
- Changes: `docs/changes/`
- Drift: `docs/drift/`
- Skills: `.agents/skills/`
- Readiness: `.pact/baseline.toml`

Delete this bootstrap file after the existing `AGENTS.md` has been integrated.
"""


def generated_entry(path: str, management: str = "seed") -> dict:
    return {
        "source": None,
        "source_path": None,
        "target": pathlib.Path(path),
        "management": management,
    }


def plan(target: pathlib.Path, github_actions: bool = False) -> list[dict]:
    operations: list[dict] = []

    for entry in source_manifest(SOURCE_ROOT):
        destination = target / entry["target"]
        legacy_rel = legacy_seed_target(entry["target"].as_posix())
        legacy_destination = target / legacy_rel if legacy_rel else None

        if destination.exists():
            action = "skip"
            reason = "already exists"
        elif legacy_destination is not None and legacy_destination.exists():
            action = "skip"
            reason = f"legacy project seed preserved at {legacy_rel}"
        else:
            action = "create"
            reason = "missing scaffold"

        operations.append({
            "action": action,
            "path": entry["target"].as_posix(),
            "source": entry["source_path"],
            "management": entry["management"],
            "reason": reason,
        })

    agents = target / "AGENTS.md"
    if agents.exists():
        rel = pathlib.Path("docs/governance/PACT_AGENT_BOOTSTRAP.md")
        destination = target / rel
        operations.append({
            "action": "skip" if destination.exists() else "create-generated",
            "path": rel.as_posix(),
            "source": None,
            "management": "seed",
            "reason": "preserve existing AGENTS.md",
        })
    else:
        operations.append({
            "action": "create-generated",
            "path": "AGENTS.md",
            "source": None,
            "management": "seed",
            "reason": "no existing AGENTS.md",
        })

    gitignore = target / ".gitignore"
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8", errors="ignore")
        if ".pact/cache/" not in text:
            operations.append({
                "action": "warn",
                "path": ".gitignore",
                "source": None,
                "management": "seed",
                "reason": "add .pact/cache/ manually; existing .gitignore is never modified",
            })
    else:
        operations.append({
            "action": "create-generated",
            "path": ".gitignore",
            "source": None,
            "management": "seed",
            "reason": "ignore derived PACT cache",
        })

    if github_actions:
        entry = github_actions_entry(SOURCE_ROOT)
        if entry:
            destination = target / entry["target"]
            operations.append({
                "action": "skip" if destination.exists() else "create",
                "path": entry["target"].as_posix(),
                "source": entry["source_path"],
                "management": entry["management"],
                "reason": (
                    "existing PACT workflow preserved"
                    if destination.exists()
                    else "opt-in PACT project CI integration"
                ),
            })

    return operations


def operation_entry(op: dict) -> dict:
    if op["source"]:
        source = SOURCE_ROOT / op["source"]
        return {
            "source": source,
            "source_path": op["source"],
            "target": pathlib.Path(op["path"]),
            "management": op["management"],
        }
    return generated_entry(op["path"], management=op["management"])


def load_install_manifest(target: pathlib.Path) -> dict | None:
    path = target / INSTALL_MANIFEST
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def write_install_manifest(
    target: pathlib.Path,
    operations: list[dict],
    created_paths: set[str],
) -> None:
    existing = load_install_manifest(target)
    files = dict(existing.get("files", {})) if existing else {}

    for op in operations:
        if op["path"] not in created_paths:
            continue
        destination = target / op["path"]
        if not destination.is_file():
            continue
        entry = operation_entry(op)
        files[op["path"]] = manifest_record(entry, destination)

    manifest = {
        "format_version": 1,
        "runtime_version": (
            existing.get("runtime_version")
            if existing
            else runtime_version(SOURCE_ROOT)
        ),
        "files": files,
    }

    path = target / INSTALL_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply(target: pathlib.Path, operations: list[dict]) -> set[str]:
    target.mkdir(parents=True, exist_ok=True)
    created: set[str] = set()

    for op in operations:
        if not op["action"].startswith("create"):
            continue

        destination = target / op["path"]
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)

        if op["source"]:
            source = SOURCE_ROOT / op["source"]
            shutil.copy2(source, destination)
        elif op["path"] == "AGENTS.md":
            destination.write_text(TARGET_AGENTS, encoding="utf-8")
        elif op["path"] == "docs/governance/PACT_AGENT_BOOTSTRAP.md":
            destination.write_text(bootstrap_snippet(), encoding="utf-8")
        elif op["path"] == ".gitignore":
            destination.write_text(".pact/cache/\n", encoding="utf-8")
        else:
            continue

        created.add(op["path"])

    write_install_manifest(target, operations, created)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely scaffold PACT into a repository")
    parser.add_argument("--target", required=True)
    parser.add_argument("--apply", action="store_true", help="write missing files; default is dry-run")
    parser.add_argument(
        "--github-actions",
        action="store_true",
        help="also create a separate PACT project workflow if that path is missing",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    target = pathlib.Path(args.target).expanduser().resolve()
    if target.exists() and not target.is_dir():
        print("PACT init: target must be a directory", file=sys.stderr)
        return 2

    operations = plan(target, github_actions=args.github_actions)

    existing_manifest = load_install_manifest(target)
    if args.apply and existing_manifest:
        installed_version = existing_manifest.get("runtime_version", "unknown")
        source_version = runtime_version(SOURCE_ROOT)
        if installed_version != source_version:
            print(
                "PACT init: this project is already tracked by a different PACT "
                f"runtime ({installed_version} != {source_version}). "
                "Use 'pact upgrade --target ...' instead of init.",
                file=sys.stderr,
            )
            return 2

    created_paths: set[str] = set()
    if args.apply:
        created_paths = apply(target, operations)

    summary = {
        "target": str(target),
        "mode": "apply" if args.apply else "dry-run",
        "source_runtime_version": runtime_version(SOURCE_ROOT),
        "github_actions": args.github_actions,
        "create": len([o for o in operations if o["action"].startswith("create")]),
        "skip": len([o for o in operations if o["action"] == "skip"]),
        "warn": len([o for o in operations if o["action"] == "warn"]),
        "created_paths": sorted(created_paths),
        "install_manifest": (
            str(target / INSTALL_MANIFEST)
            if args.apply
            else None
        ),
        "operations": operations,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"PACT init: {summary['mode']} -> {target}")
        print(f"Source runtime: {summary['source_runtime_version']}")
        for op in operations:
            print(f"- [{op['action'].upper()}] {op['path']}: {op['reason']}")
        if args.apply:
            print(f"Install manifest: {target / INSTALL_MANIFEST}")
        else:
            print("No files were written. Re-run with --apply to create missing scaffold.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
