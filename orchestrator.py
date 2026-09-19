"""Orchestrator: runs the four specialist agents (in parallel when possible)
and the arbiter, and returns one review payload.

Built as plain async/threaded Python rather than a heavier framework -- the
four agents are independent (no shared state, no cyclical handoff), so a full
graph library buys nothing here that a thread pool doesn't already give you.
`build_crewai_pipeline()` is included separately for anyone who wants the
CrewAI role-based version instead; same agents, different orchestration layer.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .agents.arbiter import run_arbiter
from .agents.base import AgentResult
from .agents.convention_agent import ConventionIndex, run_convention_agent
from .agents.correctness_agent import run_correctness_agent
from .agents.security_agent import run_security_agent
from .agents.spec_agent import run_spec_agent
from .config import Settings
from .diffing import parse_unified_diff, render_diff_for_prompt, scope_summary
from .llm import LLMClient


def review_diff(
    diff_text: str,
    intent: str,
    settings: Settings,
    convention_index: ConventionIndex | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    files = parse_unified_diff(diff_text)
    rendered = render_diff_for_prompt(files, settings.repo.max_diff_chars)
    llm = LLMClient(settings.model)

    jobs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        if settings.agents.spec:
            jobs["spec"] = pool.submit(
                run_spec_agent, llm, settings.model.reviewer_model, intent, rendered
            )
        if settings.agents.correctness:
            jobs["correctness"] = pool.submit(
                run_correctness_agent, llm, settings.model.reviewer_model, intent, rendered
            )
        if settings.agents.security:
            jobs["security"] = pool.submit(
                run_security_agent, llm, settings.model.reviewer_model, rendered
            )
        if settings.agents.convention:
            jobs["convention"] = pool.submit(
                run_convention_agent, llm, settings.model.small_model, rendered, convention_index
            )
        results = {name: job.result() for name, job in jobs.items()}

    empty = lambda name: AgentResult(agent=name, verdict="disabled")
    spec = results.get("spec", empty("spec"))
    correctness = results.get("correctness", empty("correctness"))
    security = results.get("security", empty("security"))
    convention = results.get("convention", empty("convention"))

    arbiter_out = run_arbiter(
        llm,
        settings.model.arbiter_model,
        spec,
        correctness,
        security,
        convention,
        settings.gate.block_severity,
    )

    return {
        "scope": scope_summary(files),
        "agents": {
            "spec": spec.asdict(),
            "correctness": correctness.asdict(),
            "security": security.asdict(),
            "convention": convention.asdict(),
        },
        "review": arbiter_out,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def format_markdown_review(result: dict[str, Any]) -> str:
    review = result["review"]
    sev = review.get("overall_severity", "low")
    icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(sev, "⚪")
    lines = [
        f"## {icon} PR Sentinel review -- severity: **{sev}**",
        "",
        review.get("summary", ""),
        "",
        f"_{result['scope']['files_changed']} file(s), "
        f"+{result['scope']['lines_added']}/-{result['scope']['lines_removed']} lines, "
        f"${review.get('cost_usd', 0):.4f}, {result['latency_ms']:.0f}ms_",
        "",
    ]
    findings = review.get("findings", [])
    if findings:
        lines.append("| File | Line | Severity | Agent | Finding |")
        lines.append("|---|---|---|---|---|")
        for f in findings:
            lines.append(
                f"| `{f.get('file')}` | {f.get('line') or '-'} | {f.get('severity')} | "
                f"{f.get('source_agent', '?')} | {f.get('description', '')} |"
            )
    else:
        lines.append("No findings. ✅")

    if review.get("should_block_merge"):
        lines.append("\n**⛔ Merge blocked** -- severity meets the configured threshold.")
    return "\n".join(lines)
