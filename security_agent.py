"""Security agent: injection, secrets, unsafe deserialization, authz gaps."""

from __future__ import annotations

import re

from ..llm import LLMClient, LLMError
from ..prompts import SECURITY_PROMPT, SECURITY_SYSTEM
from .base import AgentResult, Finding

# Cheap deterministic pre-screen for obvious hardcoded secrets. Runs before the
# LLM call and its hits are merged in -- regex won't miss an exact-format AWS
# key the way a model sampling at temperature 0 occasionally will.
_SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_api_key": re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"),
    "private_key_block": re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
}


def _prescan_secrets(diff_text: str) -> list[Finding]:
    findings = []
    for line in diff_text.splitlines():
        if not line.startswith("+"):
            continue
        for kind, pattern in _SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(
                    Finding(
                        file="(see diff)",
                        description=f"Possible hardcoded secret ({kind}) added in diff line",
                        severity="critical",
                        source_agent="security",
                        category="secret",
                    )
                )
    return findings


def run_security_agent(llm: LLMClient, model: str, diff_text: str) -> AgentResult:
    prescan = _prescan_secrets(diff_text)

    try:
        payload, resp = llm.complete_json(
            SECURITY_PROMPT.format(diff=diff_text),
            system=SECURITY_SYSTEM,
            model=model,
            max_tokens=1500,
        )
    except LLMError as exc:
        # A pre-scan hit still gets reported even if the LLM call fails --
        # deterministic secret detection should never depend on API uptime.
        return AgentResult(
            agent="security",
            verdict="issues_found" if prescan else "error",
            findings=prescan,
            error=str(exc),
        )

    findings = prescan + [
        Finding(
            file=item.get("file", "?"),
            line=item.get("line"),
            description=item.get("description", ""),
            severity=item.get("severity", "medium"),
            source_agent="security",
            category=item.get("category"),
        )
        for item in payload.get("findings", [])
    ]
    verdict = "issues_found" if findings else payload.get("verdict", "clean")
    return AgentResult(
        agent="security", verdict=verdict, findings=findings, raw=payload, cost_usd=resp.cost_usd()
    )
