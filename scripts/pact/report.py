#!/usr/bin/env python3
"""Compatibility entry point for pre-compact Owner Report Skill guidance."""

from __future__ import annotations

import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRY = ROOT / "pact.py"

if not ENTRY.is_file():
    print(f"PACT root entry point not found: {ENTRY}", file=sys.stderr)
    raise SystemExit(2)

sys.argv = [str(ENTRY), "report", *sys.argv[1:]]
runpy.run_path(str(ENTRY), run_name="__main__")
