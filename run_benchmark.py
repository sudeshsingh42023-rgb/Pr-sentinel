"""Benchmark: precision, recall, false-positive rate, cost per PR.

The benchmark format (`data/benchmark.jsonl`) pairs a historical PR's diff with
ground truth: did it actually have a bug that was later fixed, and roughly
where? Build this from real merged PRs plus their follow-up bugfix commits --
see BUILD_BENCHMARK.md. Never hand-write the ground truth to match what the
agent finds; that's circular and measures nothing.

A finding "matches" a labeled issue if it's in the same file and, when a line
is given, within a small window of it. This is deliberately loose: an agent
that correctly identifies the bug two lines off from your label is a hit, not
a miss -- exact line-matching would just measure your own labeling precision.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..orchestrator import review_diff

LINE_WINDOW = 5


@dataclass
class BenchmarkItem:
    id: str
    diff_path: str
    intent: str
    known_issues: list[dict[str, Any]]  # [{"file":..., "line":..., "category":...}]
    clean: bool  # True if this PR genuinely had no issues (tests false-positive rate)


def load_benchmark(path: str | Path) -> list[BenchmarkItem]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. See BUILD_BENCHMARK.md -- this file is the project."
        )
    items = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        items.append(BenchmarkItem(**row))
    return items


def _matches(finding: dict[str, Any], issue: dict[str, Any]) -> bool:
    if finding.get("file") != issue.get("file"):
        return False
    f_line, i_line = finding.get("line"), issue.get("line")
    if f_line is None or i_line is None:
        return True  # file-level match when either side lacks a line number
    return abs(int(f_line) - int(i_line)) <= LINE_WINDOW


def score_item(item: BenchmarkItem, result: dict[str, Any]) -> dict[str, Any]:
    findings = result["review"].get("findings", [])
    matched_issues = set()
    matched_findings = 0

    for f in findings:
        for i, issue in enumerate(item.known_issues):
            if i not in matched_issues and _matches(f, issue):
                matched_issues.add(i)
                matched_findings += 1
                break

    true_positives = len(matched_issues)
    false_negatives = len(item.known_issues) - true_positives
    false_positives = len(findings) - matched_findings  # findings that matched nothing

    return {
        "id": item.id,
        "clean": item.clean,
        "n_known_issues": len(item.known_issues),
        "n_findings": len(findings),
        "true_positives": true_positives,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "cost_usd": result["review"].get("cost_usd", 0.0),
        "latency_ms": result.get("latency_ms", 0.0),
        "overall_severity": result["review"].get("overall_severity"),
    }


def run_benchmark(
    benchmark_path: str | Path, settings: Settings, diff_root: str | Path = "."
) -> dict[str, Any]:
    items = load_benchmark(benchmark_path)
    diff_root = Path(diff_root)
    rows = []

    print(f"Running benchmark: {len(items)} historical PRs")
    for i, item in enumerate(items, start=1):
        diff_text = (diff_root / item.diff_path).read_text()
        try:
            result = review_diff(diff_text, item.intent, settings)
        except Exception as exc:
            print(f"  [{i}/{len(items)}] {item.id}: ERROR {exc}")
            continue
        row = score_item(item, result)
        rows.append(row)
        print(
            f"  [{i}/{len(items)}] {item.id}: TP={row['true_positives']} "
            f"FN={row['false_negatives']} FP={row['false_positives']}"
        )

    tp = sum(r["true_positives"] for r in rows)
    fn = sum(r["false_negatives"] for r in rows)
    fp = sum(r["false_positives"] for r in rows)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None

    clean_rows = [r for r in rows if r["clean"]]
    false_positive_rate_on_clean_prs = (
        sum(1 for r in clean_rows if r["n_findings"] > 0) / len(clean_rows)
        if clean_rows else None
    )

    return {
        "n_prs": len(rows),
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "false_positive_rate_on_clean_prs": (
            round(false_positive_rate_on_clean_prs, 4)
            if false_positive_rate_on_clean_prs is not None else None
        ),
        "avg_cost_per_pr_usd": round(statistics.fmean(r["cost_usd"] for r in rows), 6) if rows else 0,
        "avg_latency_ms": round(statistics.fmean(r["latency_ms"] for r in rows), 1) if rows else 0,
        "rows": rows,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default="data/benchmark.jsonl")
    parser.add_argument("--diff-root", default=".")
    parser.add_argument("--out", default="results/benchmark.json")
    args = parser.parse_args()

    settings = Settings.load()
    result = run_benchmark(args.benchmark, settings, args.diff_root)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))

    print(f"\nPrecision: {result['precision']}  Recall: {result['recall']}  F1: {result['f1']}")
    print(f"False-positive rate on clean PRs: {result['false_positive_rate_on_clean_prs']}")
    print(f"Avg cost/PR: ${result['avg_cost_per_pr_usd']}  Avg latency: {result['avg_latency_ms']}ms")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
