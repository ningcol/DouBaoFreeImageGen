#!/usr/bin/env python3
"""Inspect whether a repository has a usable PACT foundation."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

from distribution import sha256_file
from schema_validate import load_schema, validate_instance


ROOT = pathlib.Path(__file__).resolve().parents[2]

REQUIRED = [
    "AGENTS.md",
    "docs/governance/constitution.md",
    "docs/governance/truth-ownership.md",
    "docs/governance/decision-authority.md",
    "docs/governance/completion-contract.md",
    "docs/governance/human-interface.md",
    "docs/product",
    "docs/architecture",
    ".agents/decisions",
    ".agents/skills",
    ".pact/VERSION",
    ".pact/schema/artifact.schema.json",
    ".pact/schema/config.schema.json",
    ".pact/schema/install-manifest.schema.json",
    ".pact/schema/fitness.schema.json",
]


def item(name: str, state: str, detail: str) -> dict:
    return {"check": name, "state": state, "detail": detail}


def install_provenance_check(strict: bool) -> dict:
    manifest_path = ROOT / ".pact" / "install.json"
    if not manifest_path.exists():
        return item(
            "install-provenance",
            "fail" if strict else "warn",
            "missing .pact/install.json" if strict else "source/untracked checkout; no install manifest",
        )

    schema_path = ROOT / ".pact" / "schema" / "install-manifest.schema.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        errors = validate_instance(manifest, load_schema(schema_path))
        if errors:
            return item("install-provenance", "fail", "; ".join(errors))

        version_path = ROOT / ".pact" / "VERSION"
        installed_version = version_path.read_text(encoding="utf-8").strip()
        manifest_version = manifest.get("runtime_version")
        if installed_version != manifest_version:
            return item(
                "install-provenance",
                "fail",
                f"VERSION={installed_version!r} but install manifest runtime_version={manifest_version!r}",
            )

        integrity_errors = []
        for relative, record in manifest.get("files", {}).items():
            if record.get("management") != "framework":
                continue
            path = ROOT / relative
            if not path.is_file():
                integrity_errors.append(f"missing framework file: {relative}")
                continue
            actual_sha = sha256_file(path)
            expected_sha = record.get("installed_sha256")
            if actual_sha != expected_sha:
                integrity_errors.append(
                    f"framework file modified/corrupt: {relative} "
                    f"({actual_sha} != {expected_sha})"
                )

        if integrity_errors:
            return item(
                "install-provenance",
                "fail" if strict else "warn",
                "; ".join(integrity_errors[:10]),
            )

        return item(
            "install-provenance",
            "pass",
            f"runtime={manifest_version}, tracked_files={len(manifest.get('files', {}))}",
        )
    except Exception as exc:
        return item("install-provenance", "fail", f"cannot validate install manifest: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check PACT foundation health")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require project config and tracked install provenance",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks: list[dict] = []

    for relative in REQUIRED:
        path = ROOT / relative
        checks.append(
            item(
                f"path:{relative}",
                "pass" if path.exists() else "fail",
                "present" if path.exists() else "missing",
            )
        )

    owner_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "pact" / "owner.py"),
        "--json",
    ]
    if args.strict:
        owner_cmd.append("--strict")

    owner_run = subprocess.run(owner_cmd, capture_output=True, text=True)
    if owner_run.returncode != 0:
        checks.append(
            item(
                "owner-profile",
                "fail",
                (owner_run.stdout + owner_run.stderr).strip(),
            )
        )
    else:
        try:
            owner = json.loads(owner_run.stdout)
            state = "pass" if owner.get("configured") else "warn"
            detail = (
                f"{owner.get('source')} "
                f"(language={owner.get('language')}, "
                f"technical_depth={owner.get('technical_depth')})"
            )
            checks.append(item("owner-profile", state, detail))
        except json.JSONDecodeError:
            checks.append(item("owner-profile", "fail", "owner profile output was not valid JSON"))

    checks.append(install_provenance_check(args.strict))

    fitness_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "pact" / "fitness.py"),
        "--json",
        "--validate-only",
    ]
    if args.strict:
        fitness_cmd.append("--strict")

    fitness_run = subprocess.run(fitness_cmd, capture_output=True, text=True)
    if fitness_run.returncode != 0:
        checks.append(
            item(
                "architecture-fitness",
                "fail",
                (fitness_run.stdout + fitness_run.stderr).strip(),
            )
        )
    else:
        try:
            fitness = json.loads(fitness_run.stdout)
            state = "pass" if fitness.get("configured") else "warn"
            detail = (
                f"{fitness.get('config_source')} "
                f"(checks={fitness.get('check_count')})"
            )
            checks.append(item("architecture-fitness", state, detail))
        except json.JSONDecodeError:
            checks.append(
                item(
                    "architecture-fitness",
                    "fail",
                    "fitness validation output was not valid JSON",
                )
            )

    check_run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pact" / "check.py")],
        capture_output=True,
        text=True,
    )
    checks.append(
        item(
            "deterministic-check",
            "pass" if check_run.returncode == 0 else "fail",
            (check_run.stdout + check_run.stderr).strip(),
        )
    )

    try:
        with tempfile.TemporaryDirectory(prefix="pact-doctor-") as tmp:
            output = pathlib.Path(tmp) / "project-map.json"
            map_run = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "pact" / "map.py"),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            state = "pass" if map_run.returncode == 0 and output.exists() else "fail"
            detail = (map_run.stdout + map_run.stderr).strip()
            checks.append(item("project-map", state, detail))
    except Exception as exc:
        checks.append(item("project-map", "fail", str(exc)))

    overall = "fail" if any(c["state"] == "fail" for c in checks) else (
        "warn" if any(c["state"] == "warn" for c in checks) else "pass"
    )

    result = {"overall": overall, "checks": checks}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PACT doctor: {overall}")
        for check in checks:
            print(f"- [{check['state'].upper()}] {check['check']}: {check['detail']}")

    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
