#!/usr/bin/env python3
"""Plan and transactionally apply framework-managed PACT upgrades."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import tempfile

from distribution import (
    github_actions_entry,
    legacy_seed_target,
    manifest_record,
    runtime_version,
    sha256_file,
    source_manifest,
)
from schema_validate import load_schema, validate_instance


SCRIPT_ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL_MANIFEST = pathlib.Path(".pact/install.json")
MUTATING_ACTIONS = {"create-framework", "update-framework", "create-seed"}


class UpgradeApplyError(RuntimeError):
    def __init__(self, message: str, *, rolled_back: bool):
        super().__init__(message)
        self.rolled_back = rolled_back


def load_manifest(target: pathlib.Path) -> dict:
    path = target / INSTALL_MANIFEST
    if not path.exists():
        raise FileNotFoundError(
            "missing .pact/install.json; this project predates tracked PACT installs "
            "or was not initialized with a manifest"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ValueError("invalid install manifest")
    return data


def desired_entries(source_root: pathlib.Path, target: pathlib.Path, manifest: dict) -> list[dict]:
    entries = source_manifest(source_root)

    workflow_path = ".github/workflows/pact-project-check.yml"
    tracked = manifest.get("files", {}).get(workflow_path)
    if tracked or (target / workflow_path).exists():
        workflow = github_actions_entry(source_root)
        if workflow:
            entries.append(workflow)

    return entries


def plan_upgrade(source_root: pathlib.Path, target: pathlib.Path, manifest: dict) -> dict:
    tracked = manifest.get("files", {})
    entries = desired_entries(source_root, target, manifest)
    desired_by_path = {entry["target"].as_posix(): entry for entry in entries}

    operations: list[dict] = []
    conflicts: list[dict] = []
    notices: list[dict] = []

    for path, entry in sorted(desired_by_path.items()):
        destination = target / path
        source = pathlib.Path(entry["source"])
        source_sha = sha256_file(source)
        record = tracked.get(path)

        if entry["management"] == "seed":
            legacy_rel = legacy_seed_target(path)
            legacy_destination = target / legacy_rel if legacy_rel else None

            if (
                not destination.exists()
                and legacy_destination is not None
                and legacy_destination.exists()
            ):
                notices.append({
                    "kind": "legacy-seed-preserved",
                    "path": path,
                    "reason": (
                        f"legacy project-owned seed remains at {legacy_rel}; "
                        "no default TOML replacement created"
                    ),
                })
                continue

            if not destination.exists():
                operations.append({
                    "action": "create-seed",
                    "path": path,
                    "reason": "new project seed introduced by newer PACT",
                    "source_sha256": source_sha,
                })
                continue

            if record and record.get("management") == "seed":
                old_source_sha = record.get("source_sha256")
                if old_source_sha and old_source_sha != source_sha:
                    notices.append({
                        "kind": "seed-update-available",
                        "path": path,
                        "reason": (
                            "framework seed/template changed; project-owned file "
                            "will not be overwritten"
                        ),
                    })
            elif not record:
                notices.append({
                    "kind": "untracked-seed",
                    "path": path,
                    "reason": (
                        "existing project-owned file is intentionally not adopted "
                        "or overwritten"
                    ),
                })
            continue

        if not destination.exists():
            operations.append({
                "action": "create-framework",
                "path": path,
                "reason": "new or missing framework-managed file",
                "source_sha256": source_sha,
            })
            continue

        current_sha = sha256_file(destination)

        if not record:
            if current_sha == source_sha:
                notices.append({
                    "kind": "untracked-framework-identical",
                    "path": path,
                    "reason": (
                        "file matches source but has no install provenance; "
                        "not auto-adopted"
                    ),
                })
            else:
                conflicts.append({
                    "path": path,
                    "reason": (
                        "framework path exists but is not tracked by install manifest"
                    ),
                    "current_sha256": current_sha,
                    "source_sha256": source_sha,
                })
            continue

        if record.get("management") != "framework":
            notices.append({
                "kind": "ownership-changed",
                "path": path,
                "reason": (
                    "previous install marked this path project-owned; "
                    "upgrade will not overwrite it"
                ),
            })
            continue

        installed_sha = record.get("installed_sha256")
        old_source_sha = record.get("source_sha256")

        if current_sha == source_sha:
            operations.append({
                "action": "refresh-manifest",
                "path": path,
                "reason": "target already matches new framework source",
                "source_sha256": source_sha,
            })
        elif current_sha == installed_sha:
            operations.append({
                "action": "update-framework",
                "path": path,
                "reason": (
                    "target unchanged since prior install and framework source changed"
                ),
                "source_sha256": source_sha,
            })
        elif old_source_sha == source_sha:
            notices.append({
                "kind": "local-framework-modification",
                "path": path,
                "reason": (
                    "target was locally modified, but this framework file has "
                    "no upstream change in this upgrade"
                ),
            })
        else:
            conflicts.append({
                "path": path,
                "reason": (
                    "both target and framework source changed since prior install"
                ),
                "installed_sha256": installed_sha,
                "current_sha256": current_sha,
                "previous_source_sha256": old_source_sha,
                "source_sha256": source_sha,
            })

    desired_paths = set(desired_by_path)
    for path, record in sorted(tracked.items()):
        if record.get("management") == "framework" and path not in desired_paths:
            notices.append({
                "kind": "obsolete-framework-file",
                "path": path,
                "reason": (
                    "tracked framework file no longer exists in the new source; "
                    "never deleted automatically"
                ),
            })

    return {
        "from_runtime_version": manifest.get("runtime_version", "unknown"),
        "to_runtime_version": runtime_version(source_root),
        "operations": operations,
        "conflicts": conflicts,
        "notices": notices,
    }


def safe_relative_target(target: pathlib.Path, relative: str) -> pathlib.Path:
    pure = pathlib.PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise RuntimeError(f"unsafe upgrade path: {relative!r}")
    destination = (target / pathlib.Path(*pure.parts)).resolve()
    target_root = target.resolve()
    if destination != target_root and target_root not in destination.parents:
        raise RuntimeError(f"upgrade path escapes target: {relative!r}")
    return destination


def validate_new_manifest(
    target: pathlib.Path,
    new_manifest: dict,
    touched_paths: list[str],
) -> None:
    schema_path = SCRIPT_ROOT / ".pact" / "schema" / "install-manifest.schema.json"
    errors = validate_instance(new_manifest, load_schema(schema_path))
    if errors:
        raise RuntimeError("new install manifest is invalid: " + "; ".join(errors))

    version_path = target / ".pact" / "VERSION"
    actual_version = (
        version_path.read_text(encoding="utf-8").strip()
        if version_path.exists()
        else None
    )
    if actual_version != new_manifest.get("runtime_version"):
        raise RuntimeError(
            f"runtime version mismatch after apply: VERSION={actual_version!r}, "
            f"manifest={new_manifest.get('runtime_version')!r}"
        )

    files = new_manifest.get("files", {})
    for path in touched_paths:
        destination = safe_relative_target(target, path)
        record = files.get(path)
        if not destination.is_file() or not record:
            raise RuntimeError(f"upgraded file missing from final state: {path}")
        actual_sha = sha256_file(destination)
        if actual_sha != record.get("installed_sha256"):
            raise RuntimeError(
                f"upgraded file hash mismatch for {path}: "
                f"{actual_sha} != {record.get('installed_sha256')}"
            )


def cleanup_empty_parents(path: pathlib.Path, stop: pathlib.Path) -> None:
    current = path
    stop = stop.resolve()
    while current != stop and stop in current.resolve().parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def apply_upgrade(
    source_root: pathlib.Path,
    target: pathlib.Path,
    manifest: dict,
    plan: dict,
) -> dict:
    if plan["conflicts"]:
        raise UpgradeApplyError(
            "upgrade has framework conflicts; refusing automatic apply",
            rolled_back=False,
        )

    desired = {
        entry["target"].as_posix(): entry
        for entry in desired_entries(source_root, target, manifest)
    }
    files = dict(manifest.get("files", {}))

    pact_dir = target / ".pact"
    pact_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target / INSTALL_MANIFEST

    mutating_ops = [
        op for op in plan["operations"]
        if op["action"] in MUTATING_ACTIONS
    ]
    refresh_ops = [
        op for op in plan["operations"]
        if op["action"] == "refresh-manifest"
    ]

    with tempfile.TemporaryDirectory(
        prefix=".upgrade-txn-",
        dir=pact_dir,
    ) as tmp:
        txn = pathlib.Path(tmp)
        stage_root = txn / "stage"
        backup_root = txn / "backup"
        stage_root.mkdir()
        backup_root.mkdir()

        # Stage and validate every source before target mutation begins.
        staged: dict[str, pathlib.Path] = {}
        for op in mutating_ops:
            path = op["path"]
            entry = desired[path]
            staged_path = stage_root / pathlib.Path(path)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry["source"], staged_path)
            actual_sha = sha256_file(staged_path)
            if actual_sha != op["source_sha256"]:
                raise UpgradeApplyError(
                    f"staged source hash mismatch for {path}",
                    rolled_back=False,
                )
            staged[path] = staged_path

        original_exists: dict[str, bool] = {}
        backups: dict[str, pathlib.Path] = {}
        for op in mutating_ops:
            path = op["path"]
            destination = safe_relative_target(target, path)
            original_exists[path] = destination.is_file()
            if destination.is_file():
                backup = backup_root / pathlib.Path(path)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
                backups[path] = backup

        manifest_backup = backup_root / "install.json"
        shutil.copy2(manifest_path, manifest_backup)

        replaced: list[str] = []
        created: list[str] = []
        fail_after_raw = os.environ.get("PACT_TEST_FAIL_AFTER_REPLACE")
        fail_after = int(fail_after_raw) if fail_after_raw else None

        try:
            for op in mutating_ops:
                path = op["path"]
                destination = safe_relative_target(target, path)
                destination.parent.mkdir(parents=True, exist_ok=True)

                temp_destination = destination.parent / (
                    f".{destination.name}.pact-upgrade-tmp"
                )
                if temp_destination.exists():
                    temp_destination.unlink()
                shutil.copy2(staged[path], temp_destination)
                os.replace(temp_destination, destination)

                replaced.append(path)
                if not original_exists[path]:
                    created.append(path)

                if fail_after is not None and len(replaced) >= fail_after:
                    raise RuntimeError(
                        f"simulated upgrade failure after {len(replaced)} replacement(s)"
                    )

            touched = []
            for op in [*mutating_ops, *refresh_ops]:
                path = op["path"]
                entry = desired[path]
                destination = safe_relative_target(target, path)
                if destination.is_file():
                    files[path] = manifest_record(entry, destination)
                    touched.append(path)

            new_manifest = {
                "format_version": 1,
                "runtime_version": plan["to_runtime_version"],
                "files": files,
            }

            validate_new_manifest(target, new_manifest, touched)

            staged_manifest = txn / "new-install.json"
            staged_manifest.write_text(
                json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(staged_manifest, manifest_path)

            # Re-validate after committing manifest.
            validate_new_manifest(target, new_manifest, touched)
            return {
                "rolled_back": False,
                "replaced_files": len(replaced),
                "created_files": len(created),
            }

        except Exception as exc:
            rollback_errors: list[str] = []

            for path in reversed(replaced):
                destination = safe_relative_target(target, path)
                try:
                    if original_exists.get(path):
                        backup = backups[path]
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(backup, destination)
                    else:
                        if destination.exists():
                            destination.unlink()
                        cleanup_empty_parents(destination.parent, target)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{path}: {rollback_exc}")

            try:
                os.replace(manifest_backup, manifest_path)
            except Exception as rollback_exc:
                rollback_errors.append(f"install manifest: {rollback_exc}")

            message = f"upgrade apply failed and rollback was attempted: {exc}"
            if rollback_errors:
                message += "; rollback errors: " + "; ".join(rollback_errors)
            raise UpgradeApplyError(
                message,
                rolled_back=not rollback_errors,
            ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely upgrade an adopted PACT project")
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--source",
        help="PACT source root providing the newer runtime; defaults to this checkout",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="transactionally apply only when there are no framework conflicts",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    target = pathlib.Path(args.target).expanduser().resolve()
    source_root = (
        pathlib.Path(args.source).expanduser().resolve()
        if args.source
        else SCRIPT_ROOT
    )

    try:
        manifest = load_manifest(target)
        plan = plan_upgrade(source_root, target, manifest)
    except Exception as exc:
        print(f"PACT upgrade: cannot plan upgrade: {exc}", file=sys.stderr)
        return 2

    result = {
        "target": str(target),
        "source": str(source_root),
        "mode": "apply" if args.apply else "dry-run",
        **plan,
    }

    if args.apply:
        if plan["conflicts"]:
            result["applied"] = False
            result["rolled_back"] = False
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(
                    "PACT upgrade: conflicts detected; no files were changed.",
                    file=sys.stderr,
                )
                for conflict in plan["conflicts"]:
                    print(
                        f"- {conflict['path']}: {conflict['reason']}",
                        file=sys.stderr,
                    )
            return 1

        try:
            transaction = apply_upgrade(source_root, target, manifest, plan)
            result["applied"] = True
            result.update(transaction)
        except UpgradeApplyError as exc:
            result["applied"] = False
            result["rolled_back"] = exc.rolled_back
            result["apply_error"] = str(exc)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"PACT upgrade: {exc}", file=sys.stderr)
            return 2
    else:
        result["applied"] = False
        result["rolled_back"] = False

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(
        f"PACT upgrade: {plan['from_runtime_version']} -> "
        f"{plan['to_runtime_version']} ({result['mode']})"
    )
    for op in plan["operations"]:
        print(f"- [{op['action'].upper()}] {op['path']}: {op['reason']}")
    for notice in plan["notices"]:
        print(f"- [NOTICE:{notice['kind']}] {notice['path']}: {notice['reason']}")
    for conflict in plan["conflicts"]:
        print(f"- [CONFLICT] {conflict['path']}: {conflict['reason']}")

    if args.apply:
        print(
            f"Transactional apply complete: replaced={result.get('replaced_files', 0)}, "
            f"created={result.get('created_files', 0)}"
        )
    else:
        print("No files were changed. Re-run with --apply after reviewing the plan.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
