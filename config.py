"""Config for PR Sentinel: model routing, severity thresholds, agent toggles."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


@dataclass
class ModelConfig:
    provider: str = "anthropic"
    reviewer_model: str = "claude-sonnet-4-5"
    arbiter_model: str = "claude-sonnet-4-5"
    small_model: str = "claude-haiku-4-5"
    temperature: float = 0.0
    max_tokens: int = 1500


@dataclass
class AgentToggles:
    spec: bool = True
    correctness: bool = True
    security: bool = True
    convention: bool = True


@dataclass
class GateConfig:
    # Block the merge if the arbiter's max severity across findings meets/exceeds this.
    block_severity: str = "high"  # low | medium | high | critical
    max_findings_shown: int = 25
    sandbox_timeout_s: int = 60


@dataclass
class RepoConfig:
    convention_index_path: str = "data/convention_index"
    diff_context_lines: int = 8
    max_diff_chars: int = 60_000  # guard against a 5,000-line diff blowing the budget


@dataclass
class Settings:
    model: ModelConfig = field(default_factory=ModelConfig)
    agents: AgentToggles = field(default_factory=AgentToggles)
    gate: GateConfig = field(default_factory=GateConfig)
    repo: RepoConfig = field(default_factory=RepoConfig)

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides: Any) -> "Settings":
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        raw: dict[str, Any] = {}
        if path.exists():
            raw = yaml.safe_load(path.read_text()) or {}
        for section, values in overrides.items():
            if isinstance(values, dict):
                raw.setdefault(section, {}).update(values)
            else:
                raw[section] = values

        sections = {
            "model": ModelConfig,
            "agents": AgentToggles,
            "gate": GateConfig,
            "repo": RepoConfig,
        }
        kwargs = {}
        for name, klass in sections.items():
            payload = raw.get(name) or {}
            known = {k: v for k, v in payload.items() if k in klass.__annotations__}
            kwargs[name] = klass(**known)
        settings = cls(**kwargs)
        settings._apply_env()
        return settings

    def _apply_env(self) -> None:
        if v := os.getenv("SENTINEL_REVIEWER_MODEL"):
            self.model.reviewer_model = v
        if v := os.getenv("SENTINEL_BLOCK_SEVERITY"):
            self.gate.block_severity = v

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def severity_at_least(value: str, threshold: str) -> bool:
    return SEVERITY_ORDER.index(value) >= SEVERITY_ORDER.index(threshold)
