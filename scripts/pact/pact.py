#!/usr/bin/env python3
"""Compatibility entry point for pre-compact PACT project guidance."""

from __future__ import annotations

import pathlib
import runpy
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRY = ROOT / "pact.py"

if not ENTRY.is_file():
    print(f"PACT root entry point not found: {ENTRY}", file=sys.stderr)
    raise SystemExit(2)

sys.argv[0] = str(ENTRY)
runpy.run_path(str(ENTRY), run_name="__main__")
