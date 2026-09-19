"""Spec agent: does the diff match its stated intent, or has scope crept?"""

from __future__ import annotations

from ..llm import LLMClient, LLMError
from ..prompts import SPEC_PROMPT, SPEC_SYSTEM
from .base import AgentResult, Finding


def run_spec_agent(llm: LLMClient, model: str, intent: str, diff_text: str) -> AgentResult:
    try:
        payload, resp = llm.complete_json(
            SPEC_PROMPT.format(intent=intent or "(no description provided)", diff=diff_text),
            system=SPEC_SYSTEM,
            model=model,
            max_tokens=900,
        )
    except LLMError as exc:
        return AgentResult(agent="spec", verdict="error", error=str(exc))

    findings = [
        Finding(
            file=item.get("file", "?"),
            description=item.get("description", ""),
            severity=item.get("severity", "low"),
            source_agent="spec",
            category="scope_creep",
        )
        for item in payload.get("scope_creep", [])
    ]
    for missing in payload.get("missing_from_intent", []):
        findings.append(
            Finding(
                file="(intent)",
                description=f"Intent asked for this but the diff doesn't deliver it: {missing}",
                severity="medium",
                source_agent="spec",
                category="incomplete",
            )
        )

    return AgentResult(
        agent="spec",
        verdict=payload.get("verdict", "in_scope"),
        findings=findings,
        raw=payload,
        cost_usd=resp.cost_usd(),
    )
