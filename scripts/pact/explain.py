#!/usr/bin/env python3
"""Build a structured evidence packet for owner-readable project explanation."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

from schema_validate import load_schema, validate_instance

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = ROOT / ".pact" / "schema" / "explanation-packet.schema.json"


def build_index(path: pathlib.Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pact" / "map.py"),
            "--output",
            str(path),
            "--ensure",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "map failed")


def run_discovery(query: str, index: pathlib.Path, limit: int) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pact" / "discover.py"),
            query,
            "--index",
            str(index),
            "--limit",
            str(limit),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "discovery failed")
    return json.loads(result.stdout) if result.stdout.strip() else {
        "query": query,
        "result_count": 0,
        "results": [],
    }


def normalize(value: str) -> str:
    return value.casefold().strip()


def excerpt(text: str, query: str, limit: int = 700) -> str:
    if not text:
        return ""

    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean

    q = normalize(query)
    lower = normalize(clean)
    pos = lower.find(q) if q else -1

    if pos < 0:
        tokens = [t for t in re.findall(r"[\w\-]+", q, flags=re.UNICODE) if t]
        for token in tokens:
            pos = lower.find(token)
            if pos >= 0:
                break

    if pos < 0:
        return clean[:limit].rstrip() + "…"

    start = max(0, pos - limit // 3)
    end = min(len(clean), start + limit)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(clean) else ""
    return prefix + clean[start:end].strip() + suffix


def classify(doc: dict) -> str:
    typ = doc.get("artifact_type")
    path = doc.get("path", "")

    if typ in {"domain", "rule"} and doc.get("status") == "confirmed":
        return "product_truth"
    if typ == "architecture" or path.startswith("docs/architecture/"):
        return "architecture"
    if typ == "decision":
        return "decisions"
    if typ == "change":
        return "changes"
    if typ == "drift":
        return "drift"
    return "other"


def validate(packet: dict) -> list[str]:
    return validate_instance(packet, load_schema(SCHEMA))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a PACT evidence packet for project explanation"
    )
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        index_path = ROOT / ".pact" / "cache" / "project-map.json"
        build_index(index_path)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        discovery = run_discovery(args.query, index_path, max(args.limit, 1))
    except Exception as exc:
        print(f"PACT explain: setup failed: {exc}", file=sys.stderr)
        return 2

    by_path = {doc["path"]: doc for doc in index.get("documents", [])}
    selected = []
    selected_paths = set()

    for result in discovery.get("results", []):
        doc = by_path.get(result["path"])
        if not doc:
            continue
        selected.append((doc, result["score"], result.get("reasons", [])))
        selected_paths.add(doc["path"])

    domains = {
        domain
        for doc, _, _ in selected
        for domain in doc.get("domains", [])
    }

    # Expand once through explicit durable relations and shared canonical domains.
    id_to_doc = {
        doc["id"]: doc
        for doc in index.get("documents", [])
        if doc.get("id")
    }

    expansion = []
    for doc, _, _ in selected:
        for related_id in doc.get("related", []):
            related = id_to_doc.get(related_id)
            if related and related["path"] not in selected_paths:
                expansion.append((related, 35, [f"explicitly related to {doc.get('id') or doc['path']}"]))
                selected_paths.add(related["path"])

    for doc in index.get("documents", []):
        if doc["path"] in selected_paths:
            continue
        shared = domains & set(doc.get("domains", []))
        if shared:
            expansion.append((doc, 25, ["shares canonical domain: " + ", ".join(sorted(shared))]))
            selected_paths.add(doc["path"])

    combined = selected + expansion
    combined.sort(key=lambda item: (-item[1], item[0]["path"]))
    combined = combined[: max(args.limit * 2, args.limit)]

    packet = {
        "version": 1,
        "query": args.query,
        "domains": sorted(
            {
                domain
                for doc, _, _ in combined
                for domain in doc.get("domains", [])
            }
        ),
        "product_truth": [],
        "architecture": [],
        "decisions": [],
        "changes": [],
        "drift": [],
        "other": [],
        "gaps": [],
        "followup": [],
    }

    for doc, score, reasons in combined:
        item = {
            "path": doc["path"],
            "id": doc.get("id"),
            "artifact_type": doc.get("artifact_type", "document"),
            "status": doc.get("status"),
            "title": doc.get("title", doc["path"]),
            "score": int(score),
            "reasons": reasons,
            "excerpt": excerpt(doc.get("text", ""), args.query),
        }
        packet[classify(doc)].append(item)

    if not packet["product_truth"]:
        packet["gaps"].append(
            "No matching Product Truth artifact was found; do not infer normative behavior from code or architecture."
        )
        packet["followup"].append("owner-confirmation")

    if not packet["architecture"]:
        packet["gaps"].append(
            "No matching current Architecture artifact was found."
        )
        packet["followup"].append("inspect-code")

    implemented_decisions = [
        item for item in packet["decisions"]
        if item.get("status") == "implemented"
    ]
    if not implemented_decisions:
        packet["gaps"].append(
            "No implemented Decision Record was found for the current rationale; proposed, rejected, or superseded decisions must not be presented as the reason the current design exists."
        )
        packet["followup"].append("inspect-git-history")

    if packet["drift"]:
        packet["gaps"].append(
            "Known Drift is related to this query; reconcile or explain the uncertainty before presenting a definitive current-state story."
        )

    # Documentation evidence cannot by itself prove runtime behavior.
    packet["followup"].extend(["inspect-code", "inspect-tests"])
    packet["followup"] = list(dict.fromkeys(packet["followup"]))

    errors = validate(packet)
    if errors:
        print("PACT explain: generated invalid packet", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    rendered = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        output = pathlib.Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"PACT explain: evidence packet -> {output}")
        return 0

    if args.json:
        print(rendered, end="")
        return 0

    print(f"PACT explain packet for: {args.query}")
    print("This is evidence preparation, not the final semantic explanation.")
    print()
    for label in [
        "product_truth",
        "architecture",
        "decisions",
        "changes",
        "drift",
        "other",
    ]:
        items = packet[label]
        if not items:
            continue
        print(label.replace("_", " ").title() + ":")
        for item in items:
            ident = f" [{item['id']}]" if item.get("id") else ""
            print(f"- {item['title']}{ident} — {item['path']}")
        print()

    if packet["gaps"]:
        print("Gaps:")
        for gap in packet["gaps"]:
            print(f"- {gap}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
