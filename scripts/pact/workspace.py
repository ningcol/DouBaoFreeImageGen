"""Exact working-tree state binding for PACT verification receipts."""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess

from distribution import discovery_excluded_paths


GENERATED_PREFIXES = (
    ".pact/cache/",
    ".pact/runs/",
    ".pact/completions/",
    ".pact/tasks/",
    ".pact/tmp/",
)


class WorkspaceError(RuntimeError):
    pass


def _run_git(root: pathlib.Path, args: list[str], *, text: bool = False):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=text,
        timeout=30,
        check=False,
    )


def git_root(cwd: pathlib.Path) -> pathlib.Path | None:
    try:
        result = _run_git(cwd, ["rev-parse", "--show-toplevel"], text=True)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return pathlib.Path(result.stdout.strip()).resolve()


def _excluded(relative: str, installed_exclusions: set[str]) -> bool:
    normalized = relative.replace("\\", "/")
    if normalized in installed_exclusions:
        return True
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in GENERATED_PREFIXES
    )


def _hash_untracked_file(digest, root: pathlib.Path, relative: str) -> None:
    path = root / relative
    digest.update(b"untracked\0")
    digest.update(relative.encode("utf-8", errors="surrogateescape"))
    digest.update(b"\0")

    try:
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            digest.update(b"\n")
            return

        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\n")
    except OSError as exc:
        raise WorkspaceError(f"cannot fingerprint untracked file {relative}: {exc}") from exc


def git_workspace_snapshot(cwd: pathlib.Path) -> dict | None:
    root = git_root(cwd)
    if root is None:
        return None

    installed_exclusions = discovery_excluded_paths(root)

    try:
        head_result = _run_git(root, ["rev-parse", "HEAD"], text=True)
        head = head_result.stdout.strip() if head_result.returncode == 0 else None

        staged = _run_git(
            root,
            ["diff", "--cached", "--binary", "--no-ext-diff", "--"],
        )
        unstaged = _run_git(
            root,
            ["diff", "--binary", "--no-ext-diff", "--"],
        )
        untracked = _run_git(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceError(f"cannot inspect Git workspace: {exc}") from exc

    if staged.returncode != 0 or unstaged.returncode != 0 or untracked.returncode != 0:
        raise WorkspaceError("Git workspace fingerprint commands failed")

    untracked_paths = [
        item.decode("utf-8", errors="surrogateescape")
        for item in untracked.stdout.split(b"\0")
        if item
    ]
    relevant_untracked = sorted(
        relative
        for relative in untracked_paths
        if not _excluded(relative, installed_exclusions)
    )

    digest = hashlib.sha256()
    digest.update(b"PACT-WORKSPACE-V1\n")
    digest.update(f"HEAD:{head or '<none>'}\n".encode())
    digest.update(b"STAGED\n")
    digest.update(staged.stdout)
    digest.update(b"\nUNSTAGED\n")
    digest.update(unstaged.stdout)
    digest.update(b"\nUNTRACKED\n")

    for relative in relevant_untracked:
        _hash_untracked_file(digest, root, relative)

    dirty = bool(staged.stdout or unstaged.stdout or relevant_untracked)

    return {
        "kind": "git",
        "sha256": digest.hexdigest(),
        "git_head": head,
        "dirty": dirty,
        "untracked_count": len(relevant_untracked),
    }


def _filesystem_paths(root: pathlib.Path) -> list[pathlib.Path]:
    excluded_dirs = {".git", "__pycache__"}
    installed_exclusions = discovery_excluded_paths(root)
    paths: list[pathlib.Path] = []

    for current, dirs, files in os.walk(root):
        current_path = pathlib.Path(current)
        relative_dir = current_path.relative_to(root).as_posix()
        dirs[:] = [
            name
            for name in dirs
            if name not in excluded_dirs
            and not _excluded(
                (
                    f"{relative_dir}/{name}" if relative_dir != "." else name
                ).rstrip("/") + "/",
                installed_exclusions,
            )
        ]

        for name in files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if _excluded(relative, installed_exclusions):
                continue
            paths.append(path)

    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def filesystem_workspace_snapshot(cwd: pathlib.Path) -> dict:
    root = cwd.resolve()
    digest = hashlib.sha256()
    digest.update(b"PACT-WORKSPACE-FS-V1\n")

    count = 0
    for path in _filesystem_paths(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        try:
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            else:
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
        except OSError as exc:
            raise WorkspaceError(f"cannot fingerprint {relative}: {exc}") from exc
        digest.update(b"\n")
        count += 1

    return {
        "kind": "filesystem",
        "sha256": digest.hexdigest(),
        "git_head": None,
        "dirty": None,
        "untracked_count": None,
        "file_count": count,
    }


def workspace_snapshot(cwd: pathlib.Path) -> dict:
    git = git_workspace_snapshot(cwd)
    return git if git is not None else filesystem_workspace_snapshot(cwd)
