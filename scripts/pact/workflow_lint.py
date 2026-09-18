#!/usr/bin/env python3
"""Lint GitHub Actions references for immutable external action pins."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
PINNED = re.compile(r"^[^/@\s]+/[^/@\s]+@[0-9a-fA-F]{40}$")


def workflow_paths() -> list[pathlib.Path]:
    paths = list((ROOT / ".github" / "workflows").glob("*.yml"))
    paths += list((ROOT / ".github" / "workflows").glob("*.yaml"))
    paths += list((ROOT / ".pact" / "templates" / "github-actions").glob("*.yml"))
    paths += list((ROOT / ".pact" / "templates" / "github-actions").glob("*.yaml"))
    return sorted(set(path.resolve() for path in paths))


def lint(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = USES.match(line)
        if not match:
            continue
        value = match.group(1)
        if value.startswith("./") or value.startswith("docker://"):
            continue
        if not PINNED.match(value):
            errors.append(
                f"{path.relative_to(ROOT).as_posix()}:{lineno}: "
                f"external action must be pinned to a 40-char commit SHA: {value}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure external GitHub Actions use immutable commit SHAs"
    )
    parser.parse_args()

    paths = workflow_paths()
    errors: list[str] = []
    for path in paths:
        errors.extend(lint(path))

    if errors:
        print(f"PACT workflow-lint: {len(errors)} error(s)", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"PACT workflow-lint: {len(paths)} workflow/template file(s) pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
