"""Shared types for all review agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import SEVERITY_ORDER


@dataclass
class Finding:
    file: str
    description: str
    severity: str
    source_agent: str
    line: int | None = None
    category: str | None = None
    proposed_test: str | None = None

    def asdict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "description": self.description,
            "severity": self.severity,
            "source_agent": self.source_agent,
            "category": self.category,
            "proposed_test": self.proposed_test,
        }


@dataclass
class AgentResult:
    agent: str
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    error: str | None = None

    def asdict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "verdict": self.verdict,
            "findings": [f.asdict() for f in self.findings],
            "cost_usd": round(self.cost_usd, 6),
            "error": self.error,
        }


def max_severity(findings: list[Finding]) -> str:
    if not findings:
        return "low"
    return max((f.severity for f in findings), key=SEVERITY_ORDER.index)
