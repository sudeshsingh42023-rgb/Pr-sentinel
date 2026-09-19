"""Convention agent: does this diff match how *this* repo does things?

Retrieval is BM25 over a small local index of past commits/files in the repo
(built by `sentinel index-conventions`) rather than a general style opinion.
No retrieved examples -> no findings. An agent that invents a house style out
of nothing is worse than one that stays quiet.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from ..llm import LLMClient, LLMError
from ..prompts import CONVENTION_PROMPT, CONVENTION_SYSTEM
from .base import AgentResult, Finding

_TOKEN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokenize(text: str) -> list[str]:
    """Split identifiers on snake_case and camelCase so `validate_email`
    contributes both `validate` and `email` as separate BM25 terms -- code
    identifiers are the dominant vocabulary here, not English prose."""
    tokens: list[str] = []
    for raw in _TOKEN.findall(text):
        for part in raw.split("_"):
            if not part:
                continue
            tokens.extend(p.lower() for p in _CAMEL_SPLIT.split(part) if p)
    return tokens


class ConventionIndex:
    """Tiny BM25-ish index over snippets of the repo's own code."""

    def __init__(self, snippets: list[dict[str, str]]):
        self.snippets = snippets
        self.docs = [_tokenize(s["text"]) for s in snippets]
        self.df: dict[str, int] = {}
        for doc in self.docs:
            for tok in set(doc):
                self.df[tok] = self.df.get(tok, 0) + 1
        self.N = len(self.docs)

    @classmethod
    def build(cls, repo_dir: str | Path, patterns=("*.py", "*.js", "*.ts", "*.go")) -> "ConventionIndex":
        repo_dir = Path(repo_dir)
        snippets = []
        for pattern in patterns:
            for path in repo_dir.rglob(pattern):
                if any(part in {"node_modules", ".git", "venv", "__pycache__"} for part in path.parts):
                    continue
                try:
                    text = path.read_text(errors="ignore")
                except OSError:
                    continue
                # index in ~40-line windows so a match points at a usable example
                lines = text.splitlines()
                for i in range(0, len(lines), 40):
                    chunk = "\n".join(lines[i : i + 40])
                    if len(chunk.strip()) > 50:
                        snippets.append({"path": str(path.relative_to(repo_dir)), "text": chunk})
        return cls(snippets)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.snippets))

    @classmethod
    def load(cls, path: str | Path) -> "ConventionIndex":
        snippets = json.loads(Path(path).read_text())
        return cls(snippets)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, str]]:
        terms = set(_tokenize(query))
        scores = []
        for i, doc in enumerate(self.docs):
            counts = {}
            for tok in doc:
                counts[tok] = counts.get(tok, 0) + 1
            score = sum(
                counts.get(t, 0) * math.log(1 + self.N / (1 + self.df.get(t, 0)))
                for t in terms
            )
            if score > 0:
                scores.append((i, score))
        scores.sort(key=lambda x: -x[1])
        return [self.snippets[i] for i, _ in scores[:top_k]]


def run_convention_agent(
    llm: LLMClient, model: str, diff_text: str, index: ConventionIndex | None
) -> AgentResult:
    if index is None or not index.snippets:
        return AgentResult(
            agent="convention",
            verdict="skipped_no_index",
            raw={"note": "run `sentinel index-conventions` to enable this agent"},
        )

    examples = index.search(diff_text[:2000], top_k=5)
    if not examples:
        return AgentResult(agent="convention", verdict="no_matching_examples")

    example_text = "\n\n---\n\n".join(f"{e['path']}:\n{e['text']}" for e in examples)

    try:
        payload, resp = llm.complete_json(
            CONVENTION_PROMPT.format(convention_examples=example_text, diff=diff_text),
            system=CONVENTION_SYSTEM,
            model=model,
            max_tokens=900,
        )
    except LLMError as exc:
        return AgentResult(agent="convention", verdict="error", error=str(exc))

    findings = [
        Finding(
            file=item.get("file", "?"),
            line=item.get("line"),
            description=item.get("description", ""),
            severity=item.get("severity", "low"),
            source_agent="convention",
        )
        for item in payload.get("findings", [])
    ]
    return AgentResult(
        agent="convention",
        verdict=payload.get("verdict", "consistent"),
        findings=findings,
        raw=payload,
        cost_usd=resp.cost_usd(),
    )
