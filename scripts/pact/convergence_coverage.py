"""Mechanical coverage checks for task-scoped semantic Convergence."""

from __future__ import annotations

import hashlib
import pathlib


VALID_DISPOSITIONS = {
    "aligned",
    "updated",
    "stale",
    "owner-decision",
    "not-applicable",
}


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(
    context: dict,
    convergence: dict,
    *,
    root: pathlib.Path,
    context_path: pathlib.Path,
    expected_context_sha256: str | None = None,
) -> tuple[list[str], dict]:
    errors: list[str] = []

    current_context_sha256 = sha256_file(context_path)
    recorded_context_sha256 = convergence.get("context_sha256")

    if expected_context_sha256 is not None and current_context_sha256 != expected_context_sha256:
        errors.append(
            "current Task Context does not match prepared context "
            f"({current_context_sha256!r} != {expected_context_sha256!r})"
        )

    expected_binding = expected_context_sha256 or current_context_sha256
    if recorded_context_sha256 != expected_binding:
        errors.append(
            "convergence.context_sha256 does not match Task Context "
            f"({recorded_context_sha256!r} != {expected_binding!r})"
        )

    artifacts = context.get("artifacts", [])
    required_by_path: dict[str, dict] = {}
    context_duplicate_paths: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        path = item["path"]
        if path in required_by_path:
            context_duplicate_paths.append(path)
            errors.append(f"Task Context contains duplicate artifact path {path!r}")
            continue
        required_by_path[path] = item

    coverage_by_path: dict[str, dict] = {}
    duplicate_paths: list[str] = []
    unknown_paths: list[str] = []

    for item in convergence.get("coverage", []):
        path = item.get("path")
        if path in coverage_by_path:
            duplicate_paths.append(path)
            errors.append(f"duplicate Convergence coverage entry for {path!r}")
            continue
        coverage_by_path[path] = item
        if path not in required_by_path:
            unknown_paths.append(path)
            errors.append(
                f"Convergence coverage references artifact not present in Task Context: {path!r}"
            )

    missing_paths = sorted(set(required_by_path) - set(coverage_by_path))
    for path in missing_paths:
        errors.append(
            f"Task Context artifact missing from Convergence coverage: {path!r}"
        )

    updated_verified: list[str] = []
    stale_paths: list[str] = []
    owner_decision_paths: list[str] = []

    for path, item in coverage_by_path.items():
        if path not in required_by_path:
            continue

        disposition = item.get("disposition")
        if disposition not in VALID_DISPOSITIONS:
            continue

        artifact = required_by_path[path]
        prepared_sha256 = artifact.get("sha256")
        current_path = (root / path).resolve()
        try:
            current_path.relative_to(root.resolve())
        except ValueError:
            errors.append(
                f"Task Context artifact escapes repository root: {path!r}"
            )
            continue
        current_exists = current_path.is_file()

        if disposition == "updated" and prepared_sha256:
            current_sha256 = sha256_file(current_path) if current_exists else None
            if current_sha256 == prepared_sha256:
                errors.append(
                    f"Convergence marks {path!r} updated but artifact content "
                    "matches the prepared Task Context"
                )
            else:
                updated_verified.append(path)

        if disposition == "aligned" and not current_exists:
            errors.append(
                f"Convergence marks {path!r} aligned but artifact no longer exists"
            )

        if disposition == "stale":
            stale_paths.append(path)
        elif disposition == "owner-decision":
            owner_decision_paths.append(path)

    if owner_decision_paths and not any(
        finding.get("classification") == "owner-decision"
        for finding in convergence.get("findings", [])
    ):
        errors.append(
            "Convergence coverage contains owner-decision artifact(s) but "
            "no owner-decision finding provides the owner question"
        )

    stats = {
        "context_sha256": current_context_sha256,
        "required_artifacts": len(required_by_path),
        "covered_artifacts": len(
            set(required_by_path).intersection(coverage_by_path)
        ),
        "missing_artifacts": missing_paths,
        "unknown_artifacts": sorted(set(unknown_paths)),
        "duplicate_artifacts": sorted(
            set(duplicate_paths).union(context_duplicate_paths)
        ),
        "updated_verified": sorted(updated_verified),
        "stale_artifacts": sorted(stale_paths),
        "owner_decision_artifacts": sorted(owner_decision_paths),
    }
    return errors, stats
