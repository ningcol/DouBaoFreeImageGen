#!/usr/bin/env python3
"""PACT core risk policy.

Risk policy is a control-plane invariant, not project configuration. Projects
may provide stronger verification through their own tests/fitness functions,
but cannot weaken these minimum expectations.
"""

from __future__ import annotations

import argparse
import json


PROFILES = {
    "low": {
        "knowledge_limit": 8,
        "code_context_default": False,
        "code_limit": 4,
        "completion": [
            "targeted verification appropriate to the observable change",
            "blocking ambiguity must be surfaced",
        ],
    },
    "medium": {
        "knowledge_limit": 12,
        "code_context_default": True,
        "code_limit": 12,
        "completion": [
            "required passing claims need machine-backed evidence",
            "Convergence Report is required",
            "Owner Report must be evidence-backed",
        ],
    },
    "high": {
        "knowledge_limit": 20,
        "code_context_default": True,
        "code_limit": 20,
        "completion": [
            "required passing claims need machine-backed evidence",
            "inspect relevant architecture/contracts/decisions/history when applicable",
            "Evidence limitations must be resolved before completion",
            "Convergence must be fully aligned",
            "Owner Report must be evidence-backed",
        ],
    },
}


def profile(level: str) -> dict:
    if level not in PROFILES:
        raise ValueError(f"unknown risk level: {level}")
    return {"level": level, **PROFILES[level]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Show PACT core risk policy")
    parser.add_argument("level", choices=sorted(PROFILES))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = profile(args.level)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT risk: {args.level}")
        print(f"- knowledge limit: {result['knowledge_limit']}")
        print(f"- code context default: {result['code_context_default']}")
        print(f"- code limit: {result['code_limit']}")
        print("Completion requirements:")
        for requirement in result["completion"]:
            print(f"- {requirement}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
