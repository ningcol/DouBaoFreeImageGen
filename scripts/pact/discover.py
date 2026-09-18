#!/usr/bin/env python3
"""Deterministic lexical discovery over PACT project and optional code maps."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / ".pact" / "cache" / "project-map.json"
DEFAULT_CODE_INDEX = ROOT / ".pact" / "cache" / "code-map.json"


def norm(value: str) -> str:
    return value.casefold().strip()


def terms(query: str) -> list[str]:
    parts = re.findall(r"[\w\-]+", norm(query), flags=re.UNICODE)
    return [p for p in parts if p]


def score_document(doc: dict, query: str) -> tuple[int, list[str]]:
    q = norm(query)
    ts = terms(query)
    score = 0
    reasons: list[str] = []

    ident = norm(str(doc.get("id") or ""))
    title = norm(str(doc.get("title") or ""))
    aliases = [norm(str(x)) for x in doc.get("aliases", [])]
    domains = [norm(str(x)) for x in doc.get("domains", [])]
    body = norm(str(doc.get("text") or ""))

    if ident and q == ident:
        score += 200
        reasons.append("exact stable id")

    if q and q == title:
        score += 140
        reasons.append("exact title")
    elif q and q in title:
        score += 90
        reasons.append("title contains query")

    if q and q in aliases:
        score += 130
        reasons.append("exact alias")
    elif q and any(q in alias for alias in aliases):
        score += 80
        reasons.append("alias contains query")

    if q and q in domains:
        score += 90
        reasons.append("exact domain")

    if q and q in body:
        score += 45
        reasons.append("body contains query")

    matched_terms = 0
    for term in ts:
        term_score = 0
        if term == ident:
            term_score = max(term_score, 80)
        if term in title:
            term_score = max(term_score, 30)
        if any(term in alias for alias in aliases):
            term_score = max(term_score, 35)
        if any(term in domain for domain in domains):
            term_score = max(term_score, 30)
        if term in body:
            term_score = max(term_score, 8)
        if term_score:
            matched_terms += 1
            score += term_score

    if ts and matched_terms == len(ts):
        score += 20
        reasons.append("all query terms matched")

    return score, reasons


def score_code_file(item: dict, query: str) -> tuple[int, list[str]]:
    q = norm(query)
    ts = terms(query)
    path = norm(item.get("path", ""))
    name = norm(pathlib.PurePosixPath(item.get("path", "")).stem)
    symbols = [norm(x) for x in item.get("symbols", [])]
    imports = [norm(x.get("raw", "")) for x in item.get("imports", [])]

    score = 0
    reasons: list[str] = []

    if q and q == name:
        score += 140
        reasons.append("exact code file name")
    elif q and q in path:
        score += 85
        reasons.append("code path contains query")

    if q and q in symbols:
        score += 130
        reasons.append("exact symbol")
    elif q and any(q in symbol for symbol in symbols):
        score += 90
        reasons.append("symbol contains query")

    if q and any(q in raw for raw in imports):
        score += 45
        reasons.append("import text contains query")

    matched = 0
    for term in ts:
        term_score = 0
        if term in path:
            term_score = max(term_score, 18)
        if any(term in symbol for symbol in symbols):
            term_score = max(term_score, 25)
        if any(term in raw for raw in imports):
            term_score = max(term_score, 10)
        if term_score:
            matched += 1
            score += term_score

    if ts and matched == len(ts):
        score += 15
        reasons.append("all query terms matched in code metadata")

    return score, reasons


def ensure_index(path: pathlib.Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pact" / "map.py"),
            "--output",
            str(path),
            "--ensure",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def ensure_code_index(path: pathlib.Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pact" / "code_map.py"),
            "--output",
            str(path),
            "--ensure",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def ranked_code_results(code_index: dict, query: str, limit: int) -> list[dict]:
    direct = []
    for item in code_index.get("files", []):
        score, reasons = score_code_file(item, query)
        if score > 0:
            direct.append({
                "score": score,
                "reasons": reasons,
                "path": item["path"],
                "language": item["language"],
                "is_test": item["is_test"],
                "symbols": item.get("symbols", []),
                "relation": "direct-match",
                "confidence": "direct",
            })

    direct.sort(key=lambda x: (-x["score"], x["path"]))
    direct = direct[: max(limit, 1)]

    if not direct:
        return []

    direct_paths = {item["path"] for item in direct}
    neighbor_scores: dict[str, int] = {}
    neighbor_reasons: dict[str, set[str]] = {}

    for edge in code_index.get("edges", []):
        if edge["from"] in direct_paths and edge["to"] not in direct_paths:
            confidence = edge.get("confidence", "heuristic")
            base = {"relative-resolved": 35, "ast-resolved": 32, "heuristic": 24}.get(confidence, 20)
            neighbor_scores[edge["to"]] = max(neighbor_scores.get(edge["to"], 0), base)
            neighbor_reasons.setdefault(edge["to"], set()).add(
                f"imported by direct match {edge['from']} ({confidence})"
            )
        if edge["to"] in direct_paths and edge["from"] not in direct_paths:
            confidence = edge.get("confidence", "heuristic")
            base = {"relative-resolved": 40, "ast-resolved": 37, "heuristic": 28}.get(confidence, 24)
            neighbor_scores[edge["from"]] = max(neighbor_scores.get(edge["from"], 0), base)
            neighbor_reasons.setdefault(edge["from"], set()).add(
                f"imports direct match {edge['to']} ({confidence})"
            )

    by_path = {item["path"]: item for item in code_index.get("files", [])}
    neighbors = []
    for path, score in neighbor_scores.items():
        item = by_path.get(path)
        if not item:
            continue
        if item.get("is_test"):
            score += 10
        neighbors.append({
            "score": score,
            "reasons": sorted(neighbor_reasons[path]),
            "path": path,
            "language": item["language"],
            "is_test": item["is_test"],
            "symbols": item.get("symbols", []),
            "relation": "import-neighbor",
            "confidence": next(
                (
                    edge.get("confidence")
                    for edge in code_index.get("edges", [])
                    if (
                        (edge["from"] == path and edge["to"] in direct_paths)
                        or (edge["to"] == path and edge["from"] in direct_paths)
                    )
                ),
                "heuristic",
            ),
        })

    neighbors.sort(key=lambda x: (-x["score"], x["path"]))
    return direct + neighbors[: max(limit, 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover PACT project knowledge")
    parser.add_argument("query")
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--code", action="store_true", help="also search generated code relationships")
    parser.add_argument("--code-index", default=str(DEFAULT_CODE_INDEX))
    parser.add_argument("--code-limit", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    index_path = pathlib.Path(args.index)
    if not index_path.is_absolute():
        index_path = ROOT / index_path

    ensure_index(index_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))

    ranked = []
    for doc in index.get("documents", []):
        score, reasons = score_document(doc, args.query)
        if score > 0:
            ranked.append({
                "score": score,
                "reasons": reasons,
                "id": doc.get("id"),
                "artifact_type": doc.get("artifact_type"),
                "title": doc.get("title"),
                "path": doc.get("path"),
                "status": doc.get("status"),
                "domains": doc.get("domains", []),
                "related": doc.get("related", []),
                "verification": doc.get("verification", []),
            })

    ranked.sort(key=lambda x: (-x["score"], x["path"]))
    ranked = ranked[: max(args.limit, 1)]

    code_results = []
    if args.code:
        code_index_path = pathlib.Path(args.code_index)
        if not code_index_path.is_absolute():
            code_index_path = ROOT / code_index_path
        ensure_code_index(code_index_path)
        code_index = json.loads(code_index_path.read_text(encoding="utf-8"))
        code_results = ranked_code_results(code_index, args.query, args.code_limit)

    result = {
        "query": args.query,
        "result_count": len(ranked),
        "results": ranked,
        "code_result_count": len(code_results),
        "code_results": code_results,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if not ranked and not code_results:
        print(f"PACT discovery: no matches for {args.query!r}")
        return 1

    print(
        f"PACT discovery: {len(ranked)} knowledge match(es), "
        f"{len(code_results)} code match(es) for {args.query!r}"
    )
    for item in ranked:
        ident = f" [{item['id']}]" if item.get("id") else ""
        print(
            f"- {item['title']}{ident} — {item['artifact_type']} — "
            f"{item['path']} (score {item['score']})"
        )
        if item["reasons"]:
            print(f"  why: {', '.join(item['reasons'])}")

    if code_results:
        print("Code:")
        for item in code_results:
            marker = "test" if item["is_test"] else item["language"]
            print(f"- {item['path']} — {marker} — {item['relation']} (score {item['score']})")
            if item["reasons"]:
                print(f"  why: {', '.join(item['reasons'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
