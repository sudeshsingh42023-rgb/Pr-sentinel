"""Thin provider abstraction over Anthropic / OpenAI / Ollama.

Deliberately small. The point is not to reimplement LangChain -- it is to make
model swaps a one-line config change so the cost/quality ablation in the README
is honest, and to give every call a single place to emit usage telemetry.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from .config import ModelConfig


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str

    def cost_usd(self) -> float:
        rate = PRICING.get(self.model)
        if not rate:
            return 0.0
        return (self.input_tokens * rate[0] + self.output_tokens * rate[1]) / 1_000_000


# USD per million tokens (input, output). Update these before quoting costs in
# your README -- prices move, and a stale table is worse than no table.
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Synchronous chat client. One method, two shapes: text and JSON."""

    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self._client = None

    # -- public API ---------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        model = model or self.cfg.reviewer_model
        max_tokens = max_tokens or self.cfg.max_tokens
        temperature = self.cfg.temperature if temperature is None else temperature

        if self.cfg.provider == "anthropic":
            return self._anthropic(prompt, system, model, max_tokens, temperature)
        if self.cfg.provider == "openai":
            return self._openai(prompt, system, model, max_tokens, temperature)
        if self.cfg.provider == "ollama":
            return self._ollama(prompt, system, model, max_tokens, temperature)
        raise LLMError(f"unknown provider: {self.cfg.provider}")

    def complete_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any], LLMResponse]:
        """Ask for JSON and parse it defensively.

        Structured output is what makes an LLM judge aggregable instead of
        merely eloquent, so every judging and planning node goes through here.
        """
        system = (system or "") + (
            "\n\nRespond with a single valid JSON object and nothing else. "
            "No prose, no explanation, no markdown code fences."
        )
        resp = self.complete(prompt, system=system, model=model, max_tokens=max_tokens)
        return _parse_json(resp.text), resp

    # -- providers ----------------------------------------------------------

    def _anthropic(self, prompt, system, model, max_tokens, temperature) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("pip install anthropic") from exc

        if self._client is None:
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise LLMError("ANTHROPIC_API_KEY is not set (see .env.example)")
            self._client = anthropic.Anthropic(api_key=key, timeout=self.cfg.timeout_s)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        msg = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return LLMResponse(
            text=text,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            model=model,
            provider="anthropic",
        )

    def _openai(self, prompt, system, model, max_tokens, temperature) -> LLMResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError("pip install openai") from exc

        if self._client is None:
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                raise LLMError("OPENAI_API_KEY is not set (see .env.example)")
            self._client = OpenAI(api_key=key, timeout=self.cfg.timeout_s)

        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        usage = resp.usage
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=model,
            provider="openai",
        )

    def _ollama(self, prompt, system, model, max_tokens, temperature) -> LLMResponse:
        """Local fallback so the pipeline is runnable with zero API spend."""
        import urllib.request

        body = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "system": system or "",
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
        ).encode()
        req = urllib.request.Request(
            os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as fh:
            payload = json.loads(fh.read())
        return LLMResponse(
            text=payload.get("response", ""),
            input_tokens=payload.get("prompt_eval_count", 0),
            output_tokens=payload.get("eval_count", 0),
            model=model,
            provider="ollama",
        )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_json(text: str) -> dict[str, Any]:
    """Models fence their JSON roughly 30% of the time regardless of the prompt."""
    text = text.strip()
    if m := _FENCE.search(text):
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError(f"could not parse JSON from model output: {text[:300]!r}")
