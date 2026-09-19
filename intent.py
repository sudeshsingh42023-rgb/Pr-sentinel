"""Structured intent specs for AI coding agents, and an A/B harness comparing
task success with vs without the structured spec.

This directly answers the JD line "specify intent prompts for AI coding
agents". The claim to test: a bounded YAML spec (goal, scope, constraints,
acceptance tests) produces a higher first-pass success rate than a freeform
prompt of similar length, because it removes the two failure modes coding
agents hit most -- scope creep and silently skipped acceptance criteria.

    python -m pr_sentinel.intent --tasks intent/tasks.jsonl --out results/

This does NOT invoke a real coding agent in this scaffold (no network here).
It defines the exact protocol and scoring so you can run it against whichever
coding agent you have access to (Claude Code, Cursor, Copilot Workspace, or
your own harness calling an LLM to write a patch).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .llm import LLMClient
from .prompts import INTENT_EXPANSION_PROMPT, INTENT_EXPANSION_SYSTEM


@dataclass
class IntentSpec:
    goal: str
    in_scope_files: list[str]
    out_of_scope: list[str]
    constraints: list[str]
    acceptance_tests: list[str]

    def to_yaml(self) -> str:
        return yaml.safe_dump(asdict(self), sort_keys=False)


def expand_task_to_spec(llm: LLMClient, model: str, task: str, repo_context: str = "") -> IntentSpec:
    payload, _ = llm.complete_json(
        INTENT_EXPANSION_PROMPT.format(task=task, repo_context=repo_context or "(none provided)"),
        system=INTENT_EXPANSION_SYSTEM,
        model=model,
        max_tokens=700,
    )
    return IntentSpec(
        goal=payload.get("goal", task),
        in_scope_files=payload.get("in_scope_files", []),
        out_of_scope=payload.get("out_of_scope", []),
        constraints=payload.get("constraints", []),
        acceptance_tests=payload.get("acceptance_tests", []),
    )


@dataclass
class TaskResult:
    task_id: str
    condition: str  # "freeform" | "structured"
    acceptance_tests_passed: int
    acceptance_tests_total: int
    scope_violations: int  # files touched outside in_scope_files
    diff_char_count: int

    @property
    def success_rate(self) -> float:
        return (
            self.acceptance_tests_passed / self.acceptance_tests_total
            if self.acceptance_tests_total else 0.0
        )


def score_diff_against_spec(
    diff_files_touched: list[str], spec: IntentSpec, tests_passed: int, tests_total: int,
) -> dict[str, Any]:
    """Score a coding agent's diff against the structured spec.

    Call this after running the agent under the "structured" condition, with
    the acceptance tests executed via the sandbox module and their pass count.
    """
    in_scope = set(spec.in_scope_files)
    violations = [f for f in diff_files_touched if in_scope and f not in in_scope]
    return {
        "acceptance_tests_passed": tests_passed,
        "acceptance_tests_total": tests_total,
        "scope_violations": len(violations),
        "violating_files": violations,
    }


def summarize(results: list[TaskResult]) -> dict[str, Any]:
    by_condition: dict[str, list[TaskResult]] = {}
    for r in results:
        by_condition.setdefault(r.condition, []).append(r)

    out = {}
    for condition, rows in by_condition.items():
        out[condition] = {
            "n_tasks": len(rows),
            "mean_success_rate": round(sum(r.success_rate for r in rows) / len(rows), 4),
            "mean_scope_violations": round(sum(r.scope_violations for r in rows) / len(rows), 4),
            "total_acceptance_tests_passed": sum(r.acceptance_tests_passed for r in rows),
            "total_acceptance_tests": sum(r.acceptance_tests_total for r in rows),
        }
    return out


def main() -> None:
    """CLI stub documenting the exact protocol -- fill in a call to whatever
    coding agent you're comparing (Claude Code, Cursor, etc.) and then call
    `summarize()` on the collected TaskResults."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="intent/tasks.jsonl")
    parser.add_argument("--out", default="results/intent_ab.json")
    args = parser.parse_args()

    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"{tasks_path} not found. See intent/README.md to build your task set.")
        return

    print(
        "This harness defines the scoring protocol but does not call a live coding "
        "agent in this offline scaffold. Wire in a call to your agent of choice, "
        "run both conditions, then call summarize(). See intent/README.md."
    )


if __name__ == "__main__":
    main()
