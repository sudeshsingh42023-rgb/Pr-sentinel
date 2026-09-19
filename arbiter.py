"""Arbiter: merges the four specialist outputs into one review + gate decision."""

from __future__ import annotations

import json

from ..config import SEVERITY_ORDER, severity_at_least
from ..llm import LLMClient, LLMError
from ..prompts import ARBITER_PROMPT, ARBITER_SYSTEM
from .base import AgentResult, Finding, max_severity


def run_arbiter(
    llm: LLMClient,
    model: str,
    spec: AgentResult,
    correctness: AgentResult,
    security: AgentResult,
    convention: AgentResult,
    block_severity: str,
) -> dict:
    all_findings = spec.findings + correctness.findings + security.findings + convention.findings

    if not all_findings:
        return {
            "overall_severity": "low",
            "should_block_merge": False,
            "summary": "No issues found by the reviewer crew.",
            "findings": [],
            "cost_usd": spec.cost_usd + correctness.cost_usd + security.cost_usd + convention.cost_usd,
        }

    try:
        payload, resp = llm.complete_json(
            ARBITER_PROMPT.format(
                spec=json.dumps(spec.raw), correctness=json.dumps(correctness.raw),
                security=json.dumps(security.raw), convention=json.dumps(convention.raw),
            ),
            system=ARBITER_SYSTEM,
            model=model,
            max_tokens=1500,
        )
        cost = resp.cost_usd()
    except LLMError:
        # Deterministic fallback: don't lose findings just because the merge
        # call failed. Dedup by (file, description) and take the max severity.
        seen = {}
        for f in all_findings:
            key = (f.file, f.description[:80])
            if key not in seen or SEVERITY_ORDER.index(f.severity) > SEVERITY_ORDER.index(seen[key].severity):
                seen[key] = f
        merged = list(seen.values())
        sev = max_severity(merged)
        payload = {
            "overall_severity": sev,
            "should_block_merge": severity_at_least(sev, block_severity),
            "summary": f"{len(merged)} finding(s) across spec/correctness/security/convention agents "
                       "(arbiter LLM call failed; falling back to deterministic merge).",
            "findings": [f.asdict() for f in merged],
        }
        cost = 0.0

    total_cost = (
        spec.cost_usd + correctness.cost_usd + security.cost_usd + convention.cost_usd + cost
    )
    payload["cost_usd"] = round(total_cost, 6)
    payload.setdefault(
        "should_block_merge",
        severity_at_least(payload.get("overall_severity", "low"), block_severity),
    )
    return payload
