"""Ignore-aware repository file enumeration for generated PACT indexes."""

from __future__ import annotations

import os
import pathlib
import subprocess
from collections.abc import Iterable


DEFAULT_PRUNE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    "out",
    "vendor",
    "__pycache__",
    ".pact/cache",
}


def git_visible_files(root: pathlib.Path) -> list[pathlib.Path] | None:
    """Return tracked + visible untracked files, or None when Git is unavailable."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None

        result = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    paths: set[pathlib.Path] = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape")
        candidate = root / pathlib.Path(relative)
        if candidate.is_file():
            paths.add(candidate)

    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def walk_visible_files(
    root: pathlib.Path,
    *,
    prune_dirs: Iterable[str] = DEFAULT_PRUNE_DIRS,
) -> list[pathlib.Path]:
    """Fallback enumeration that prunes unwanted directories before descending."""
    prune = set(prune_dirs)
    paths: list[pathlib.Path] = []

    for current, dirs, files in os.walk(root):
        current_path = pathlib.Path(current)
        relative_dir = current_path.relative_to(root).as_posix()

        kept = []
        for name in dirs:
            relative = name if relative_dir == "." else f"{relative_dir}/{name}"
            if name in prune or relative in prune:
                continue
            kept.append(name)
        dirs[:] = kept

        for name in files:
            path = current_path / name
            if path.is_file():
                paths.append(path)

    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def repository_files(root: pathlib.Path) -> tuple[list[pathlib.Path], str]:
    """Return visible repository files and the enumeration mode used."""
    git_paths = git_visible_files(root)
    if git_paths is not None:
        return git_paths, "git"
    return walk_visible_files(root), "filesystem"
