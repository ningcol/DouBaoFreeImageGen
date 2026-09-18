#!/usr/bin/env python3
"""Show PACT framework/runtime install version information."""

from __future__ import annotations

import argparse
import json
import pathlib


SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2]


def source_version(root: pathlib.Path) -> str:
    path = root / ".pact" / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Show PACT runtime version")
    parser.add_argument("--target", help="optional adopted project to inspect")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = {
        "source_runtime_version": source_version(SOURCE_ROOT),
    }

    if args.target:
        target = pathlib.Path(args.target).expanduser().resolve()
        manifest = target / ".pact" / "install.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            result["target"] = str(target)
            result["installed_runtime_version"] = data.get("runtime_version", "unknown")
            result["tracked_files"] = len(data.get("files", {}))
        else:
            result["target"] = str(target)
            result["installed_runtime_version"] = None
            result["tracked_files"] = 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT runtime: {result['source_runtime_version']}")
        if args.target:
            print(f"Target runtime: {result['installed_runtime_version'] or 'untracked'}")
            print(f"Tracked install files: {result['tracked_files']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
