"""Correctness agent: bugs, edge cases, proposed tests. No style comments."""

from __future__ import annotations

from ..llm import LLMClient, LLMError
from ..prompts import CORRECTNESS_PROMPT, CORRECTNESS_SYSTEM
from .base import AgentResult, Finding


def run_correctness_agent(
    llm: LLMClient, model: str, intent: str, diff_text: str
) -> AgentResult:
    try:
        payload, resp = llm.complete_json(
            CORRECTNESS_PROMPT.format(intent=intent or "(no description provided)", diff=diff_text),
            system=CORRECTNESS_SYSTEM,
            model=model,
            max_tokens=1500,
        )
    except LLMError as exc:
        return AgentResult(agent="correctness", verdict="error", error=str(exc))

    findings = [
        Finding(
            file=item.get("file", "?"),
            line=item.get("line"),
            description=item.get("description", ""),
            severity=item.get("severity", "medium"),
            source_agent="correctness",
            proposed_test=item.get("proposed_test"),
        )
        for item in payload.get("findings", [])
    ]
    return AgentResult(
        agent="correctness",
        verdict=payload.get("verdict", "clean"),
        findings=findings,
        raw=payload,
        cost_usd=resp.cost_usd(),
    )
