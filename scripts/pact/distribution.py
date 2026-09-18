"""Shared PACT distribution/install metadata helpers."""

from __future__ import annotations

import hashlib
import json
import pathlib


FRAMEWORK_DOCS = [
    "pact.py",
    "docs/product/README.md",
    "docs/product/glossary/README.md",
    "docs/product/domains/README.md",
    "docs/product/domains/TEMPLATE.md",
    "docs/product/rules/README.md",
    "docs/product/rules/TEMPLATE.md",
    "docs/architecture/README.md",
    "docs/changes/README.md",
    "docs/changes/TEMPLATE.md",
    "docs/changes/active/README.md",
    "docs/changes/completed/README.md",
    "docs/changes/abandoned/README.md",
    "docs/drift/README.md",
    "docs/drift/TEMPLATE.md",
    "docs/drift/known/README.md",
    "docs/drift/resolved/README.md",
    "docs/drift/accepted/README.md",
    "docs/initialization.md",
    "docs/initialization-checklist.md",
    "docs/evaluation/pilot-scorecard.md",
    ".agents/decisions/README.md",
    ".agents/decisions/TEMPLATE.md",
    ".agents/decisions/proposed/README.md",
    ".agents/decisions/implemented/README.md",
    ".agents/decisions/rejected/README.md",
    ".agents/decisions/archived/README.md",
    ".pact/VERSION",
]

SEED_SOURCE_MAPPINGS = [
    (".pact/config.example.toml", ".pact/config.toml"),
    (".pact/baseline.example.toml", ".pact/baseline.toml"),
    (".pact/fitness.example.toml", ".pact/fitness.toml"),
]

LEGACY_SEED_TARGETS = {
    ".pact/config.toml": ".pact/config.yaml",
    ".pact/baseline.toml": ".pact/baseline.yaml",
    ".pact/fitness.toml": ".pact/fitness.yaml",
}


def legacy_seed_target(target_rel: str) -> str | None:
    return LEGACY_SEED_TARGETS.get(target_rel)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_version(source_root: pathlib.Path) -> str:
    path = source_root / ".pact" / "VERSION"
    if not path.exists():
        return "unknown"
    return path.read_text(encoding="utf-8").strip() or "unknown"


def source_manifest(source_root: pathlib.Path) -> list[dict]:
    """Return files PACT may seed/manage in an adopted project.

    management=framework:
      may be upgraded automatically only when unchanged since the prior install.

    management=seed:
      project-owned after creation; never overwritten by upgrade.
    """
    entries: list[dict] = []

    def add(source_rel: str, target_rel: str | None = None, management: str = "framework") -> None:
        source = source_root / source_rel
        if not source.exists() or not source.is_file():
            return
        entries.append({
            "source": source,
            "source_path": source_rel,
            "target": pathlib.Path(target_rel or source_rel),
            "management": management,
        })

    for path in sorted((source_root / "docs" / "governance").glob("*.md")):
        entries.append({
            "source": path,
            "source_path": path.relative_to(source_root).as_posix(),
            "target": path.relative_to(source_root),
            "management": "seed",
        })

    for rel in FRAMEWORK_DOCS:
        add(rel)

    for path in sorted((source_root / ".agents" / "skills").glob("*.md")):
        entries.append({
            "source": path,
            "source_path": path.relative_to(source_root).as_posix(),
            "target": path.relative_to(source_root),
            "management": "seed",
        })

    for path in sorted((source_root / ".pact" / "schema").glob("*.json")):
        entries.append({
            "source": path,
            "source_path": path.relative_to(source_root).as_posix(),
            "target": path.relative_to(source_root),
            "management": "framework",
        })

    runtime_dir = source_root / "scripts" / "pact"
    if runtime_dir.exists():
        for path in sorted(runtime_dir.iterdir()):
            if (
                path.is_file()
                and path.suffix in {".py", ".md", ".txt"}
                and path.name != "__pycache__"
            ):
                entries.append({
                    "source": path,
                    "source_path": path.relative_to(source_root).as_posix(),
                    "target": path.relative_to(source_root),
                    "management": "framework",
                })

    for source_rel, target_rel in SEED_SOURCE_MAPPINGS:
        add(source_rel, target_rel, management="seed")

    return entries


def github_actions_entry(source_root: pathlib.Path) -> dict | None:
    source_rel = ".pact/templates/github-actions/pact-project-check.yml"
    source = source_root / source_rel
    if not source.exists():
        return None
    return {
        "source": source,
        "source_path": source_rel,
        "target": pathlib.Path(".github/workflows/pact-project-check.yml"),
        "management": "framework",
    }


def manifest_record(entry: dict, destination: pathlib.Path) -> dict:
    source = entry.get("source")
    source_sha = sha256_file(source) if source and pathlib.Path(source).is_file() else None
    return {
        "management": entry["management"],
        "source_path": entry.get("source_path"),
        "source_sha256": source_sha,
        "installed_sha256": sha256_file(destination),
    }


def discovery_excluded_paths(root: pathlib.Path) -> set[str]:
    """Return installed PACT scaffold paths that are not target project knowledge.

    - framework-managed files are always excluded from target Project/Code maps;
    - project-owned seed files are excluded only while byte-identical to the
      installed scaffold; once edited by the project they become discoverable.

    A PACT source checkout without .pact/install.json returns no exclusions.
    """
    manifest_path = root / ".pact" / "install.json"
    if not manifest_path.is_file():
        return set()

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    files = manifest.get("files")
    if not isinstance(files, dict):
        return set()

    excluded: set[str] = set()
    for relative, record in files.items():
        if not isinstance(relative, str) or not isinstance(record, dict):
            continue

        management = record.get("management")
        if management == "framework":
            excluded.add(relative)
            continue

        if management != "seed":
            continue

        path = root / relative
        expected = record.get("installed_sha256")
        if not path.is_file() or not isinstance(expected, str):
            continue

        try:
            actual = sha256_file(path)
        except OSError:
            continue

        if actual == expected:
            excluded.add(relative)

    return excluded
