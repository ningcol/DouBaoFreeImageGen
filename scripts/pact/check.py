#!/usr/bin/env python3
"""Deterministic PACT repository checks."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass
from urllib.parse import unquote

from formats import parse_markdown_metadata
from schema_validate import load_schema, validate_instance


STATUS_BY_TYPE = {
    "domain": {"candidate", "confirmed", "superseded", "retired"},
    "rule": {"candidate", "confirmed", "superseded", "retired"},
    "decision": {"proposed", "implemented", "rejected", "superseded", "archived"},
    "change": {"active", "completed", "abandoned"},
    "drift": {"known", "resolved", "accepted"},
    "architecture": {"current", "deprecated"},
}

PATH_PREFIX_BY_TYPE = {
    "domain": ("docs/product/domains/",),
    "rule": ("docs/product/rules/",),
    "decision": (".agents/decisions/",),
    "change": ("docs/changes/",),
    "drift": ("docs/drift/",),
    "architecture": ("docs/architecture/",),
}

ID_REQUIRED = {"domain", "rule", "decision", "drift"}
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
    "javascript:",
)
MANAGED_ROOT_FILES = {"README.md", "AGENTS.md"}
MANAGED_PREFIXES = ("docs/", ".agents/")


@dataclass
class Artifact:
    path: pathlib.Path
    pact: dict
    metadata_format: str | None


def rel(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def is_managed_markdown(path: pathlib.Path, root: pathlib.Path) -> bool:
    relative = rel(path, root)
    return relative in MANAGED_ROOT_FILES or relative.startswith(MANAGED_PREFIXES)


def read_artifact(path: pathlib.Path) -> Artifact | None:
    raw = path.read_text(encoding="utf-8")
    data, _, metadata_format = parse_markdown_metadata(raw)
    pact = data.get("pact") if isinstance(data, dict) else None
    if pact is None:
        return None
    if not isinstance(pact, dict):
        raise ValueError("front matter table 'pact' must be an object/table")
    return Artifact(path=path, pact=pact, metadata_format=metadata_format)


def discover(root: pathlib.Path) -> tuple[list[Artifact], list[str]]:
    artifacts: list[Artifact] = []
    errors: list[str] = []

    for path in sorted(root.rglob("*.md")):
        if not is_managed_markdown(path, root):
            continue
        relative = rel(path, root)
        if relative.endswith("/TEMPLATE.md") or relative == "TEMPLATE.md":
            continue
        try:
            artifact = read_artifact(path)
            if artifact:
                artifacts.append(artifact)
        except Exception as exc:
            errors.append(f"{relative}: invalid PACT front matter: {exc}")

    return artifacts, errors


def lifecycle_errors(path: str, typ: str | None, status: str | None) -> list[str]:
    errors: list[str] = []

    if typ == "decision":
        if "/proposed/" in path and status != "proposed":
            errors.append(f"{path}: proposed decision path requires status 'proposed'")
        if "/implemented/" in path and status not in {"implemented", "superseded"}:
            errors.append(
                f"{path}: implemented decision path requires status 'implemented' or 'superseded'"
            )
        if "/rejected/" in path and status != "rejected":
            errors.append(f"{path}: rejected decision path requires status 'rejected'")
        if "/archived/" in path and status != "archived":
            errors.append(f"{path}: archived decision path requires status 'archived'")

    if typ == "drift":
        if "/known/" in path and status != "known":
            errors.append(f"{path}: known drift path requires status 'known'")
        if "/resolved/" in path and status != "resolved":
            errors.append(f"{path}: resolved drift path requires status 'resolved'")
        if "/accepted/" in path and status != "accepted":
            errors.append(f"{path}: accepted drift path requires status 'accepted'")

    if typ == "change":
        if "/active/" in path and status != "active":
            errors.append(f"{path}: active change path requires status 'active'")
        if "/completed/" in path and status != "completed":
            errors.append(f"{path}: completed change path requires status 'completed'")
        if "/abandoned/" in path and status != "abandoned":
            errors.append(f"{path}: abandoned change path requires status 'abandoned'")

    return errors


def validate_artifacts(artifacts: list[Artifact], root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    schema = load_schema(root / ".pact" / "schema" / "artifact.schema.json")
    seen_ids: dict[str, Artifact] = {}

    for artifact in artifacts:
        path = rel(artifact.path, root)
        wrapper = {"pact": artifact.pact}

        for error in validate_instance(wrapper, schema):
            errors.append(f"{path}: schema error at {error}")

        typ = artifact.pact.get("type")
        status = artifact.pact.get("status")
        ident = artifact.pact.get("id")

        if typ in ID_REQUIRED and not ident:
            errors.append(f"{path}: type '{typ}' requires a stable id")

        if ident:
            previous = seen_ids.get(ident)
            if previous:
                errors.append(
                    f"{path}: duplicate stable id '{ident}' already used by "
                    f"{rel(previous.path, root)}"
                )
            else:
                seen_ids[ident] = artifact

        if typ in STATUS_BY_TYPE and status is not None and status not in STATUS_BY_TYPE[typ]:
            allowed = ", ".join(sorted(STATUS_BY_TYPE[typ]))
            errors.append(
                f"{path}: invalid status '{status}' for type '{typ}' (allowed: {allowed})"
            )

        prefixes = PATH_PREFIX_BY_TYPE.get(typ)
        if prefixes and not path.startswith(prefixes):
            errors.append(
                f"{path}: type '{typ}' must live under one of: {', '.join(prefixes)}"
            )

        errors.extend(lifecycle_errors(path, typ, status))

    for artifact in artifacts:
        path = rel(artifact.path, root)
        typ = artifact.pact.get("type")
        ident = artifact.pact.get("id")

        for domain_id in artifact.pact.get("domains", []) or []:
            target = seen_ids.get(domain_id)
            if not target:
                errors.append(f"{path}: domains references missing id '{domain_id}'")
            elif target.pact.get("type") != "domain":
                errors.append(
                    f"{path}: domains reference '{domain_id}' must target type 'domain', "
                    f"found '{target.pact.get('type')}'"
                )

        for field in ("related", "supersedes"):
            for target_id in artifact.pact.get(field, []) or []:
                target = seen_ids.get(target_id)
                if not target:
                    errors.append(f"{path}: {field} references missing id '{target_id}'")
                    continue
                if target_id == ident:
                    errors.append(f"{path}: {field} must not reference itself ('{target_id}')")
                if field == "supersedes" and target.pact.get("type") != typ:
                    errors.append(
                        f"{path}: supersedes '{target_id}' must target the same artifact type"
                    )

        superseded_by = artifact.pact.get("superseded_by")
        if superseded_by:
            target = seen_ids.get(superseded_by)
            if not target:
                errors.append(
                    f"{path}: superseded_by references missing id '{superseded_by}'"
                )
            else:
                if superseded_by == ident:
                    errors.append(
                        f"{path}: superseded_by must not reference itself ('{superseded_by}')"
                    )
                if target.pact.get("type") != typ:
                    errors.append(
                        f"{path}: superseded_by '{superseded_by}' must target the same artifact type"
                    )

    return errors


def clean_link(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    if " " in value and not value.startswith(("http://", "https://")):
        value = value.split(" ", 1)[0]
    return unquote(value)


def validate_links(root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    root_resolved = root.resolve()

    for path in sorted(root.rglob("*.md")):
        if not is_managed_markdown(path, root):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for raw in MD_LINK.findall(text):
            link = clean_link(raw)
            if not link or link.startswith("#") or link.startswith(EXTERNAL_PREFIXES):
                continue

            destination = link.split("#", 1)[0].split("?", 1)[0]
            if not destination:
                continue

            target = (
                root / destination.lstrip("/")
                if destination.startswith("/")
                else path.parent / destination
            )
            resolved = target.resolve()

            if resolved != root_resolved and root_resolved not in resolved.parents:
                # A relative Markdown destination that escapes the repository file
                # tree may intentionally navigate to hosting UI routes, e.g.
                # ../../actions/workflows/... from a GitHub README. The machine
                # cannot establish that such a destination is broken, so this is
                # outside the deterministic FAIL boundary.
                continue

            if not resolved.exists():
                errors.append(f"{rel(path, root)}: broken internal link '{raw}'")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic PACT checks")
    parser.add_argument(
        "--root",
        help="repository root to validate; defaults to the repository containing this script",
    )
    args = parser.parse_args()

    default_root = pathlib.Path(__file__).resolve().parents[2]
    root = pathlib.Path(args.root).expanduser().resolve() if args.root else default_root

    schema = root / ".pact" / "schema" / "artifact.schema.json"
    if not schema.exists():
        print(f"PACT: missing artifact schema at {schema}", file=sys.stderr)
        return 2

    artifacts, errors = discover(root)
    errors.extend(validate_artifacts(artifacts, root))
    errors.extend(validate_links(root))

    print(f"PACT: discovered {len(artifacts)} machine-readable artifact(s).")

    if errors:
        print(f"PACT: {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    legacy = sum(a.metadata_format == "legacy-yaml" for a in artifacts)
    if legacy:
        print(
            f"PACT: {legacy} legacy YAML artifact(s) remain readable; "
            "new/edited artifacts should use TOML front matter."
        )

    print("PACT: deterministic checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
