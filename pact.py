#!/usr/bin/env python3
"""Convenient repository-root entry point for PACT."""

from __future__ import annotations

import pathlib
import runpy
import sys


if sys.version_info < (3, 11):
    print(
        "PACT 0.3 requires Python 3.11+ (stdlib tomllib is used).",
        file=sys.stderr,
    )
    raise SystemExit(2)

ROOT = pathlib.Path(__file__).resolve().parent
RUNTIME = ROOT / "scripts" / "pact" / "pact.py"

if not RUNTIME.exists():
    print(f"PACT runtime not found: {RUNTIME}", file=sys.stderr)
    raise SystemExit(2)

sys.argv[0] = str(RUNTIME)
runpy.run_path(str(RUNTIME), run_name="__main__")
