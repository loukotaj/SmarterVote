"""Token cost accounting for the agent pipeline.

A single ``ContextVar`` (``_cost_ctx``) carries a per-run accumulator dict
for the active async task.  Both ``agent.py`` (OpenAI calls) and
``review.py`` (Claude / Gemini / Grok calls) write to it via ``accumulate()``.
``agent.py`` reads the totals at the end of ``run_agent()`` to produce the
``agent_metrics`` block.
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional

# ContextVar holds the live accumulator for the current run (async-safe).
# Shape: {"prompt_tokens": int, "completion_tokens": int,
#          "model_breakdown": {model: {"prompt_tokens": int, "completion_tokens": int}}}
_cost_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("_cost_ctx", default=None)

# ---------------------------------------------------------------------------
# Approximate list prices per million tokens (USD, as of mid-2025)
# ---------------------------------------------------------------------------

OPENAI_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-5.4":      {"input": 2.50, "output": 10.00},
    "gpt-5.4-mini": {"input": 0.15, "output":  0.60},
}

ANTHROPIC_PRICING: Dict[str, Dict[str, float]] = {
    "claude-sonnet-4-6":           {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001":   {"input": 0.80, "output":  4.00},
    # Legacy model names
    "claude-3-5-sonnet-20241022":  {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307":     {"input": 0.25, "output":  1.25},
}

GEMINI_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-3-flash-preview":        {"input": 0.10, "output": 0.40},
    "gemini-3.1-flash-lite-preview": {"input": 0.05, "output": 0.20},
}

GROK_PRICING: Dict[str, Dict[str, float]] = {
    "grok-3":      {"input": 3.00, "output": 15.00},
    "grok-3-mini": {"input": 0.30, "output":  0.50},
}

_ALL_PRICING = {**OPENAI_PRICING, **ANTHROPIC_PRICING, **GEMINI_PRICING, **GROK_PRICING}
_DEFAULT_INPUT_PER_M  = 2.50
_DEFAULT_OUTPUT_PER_M = 10.00


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated USD cost for a single model call."""
    p = _ALL_PRICING.get(model, {"input": _DEFAULT_INPUT_PER_M, "output": _DEFAULT_OUTPUT_PER_M})
    return prompt_tokens / 1_000_000 * p["input"] + completion_tokens / 1_000_000 * p["output"]


def accumulate(prompt_tokens: int, completion_tokens: int, model: str = "") -> None:
    """Add token counts to the live run accumulator (no-op if no run is active)."""
    acc = _cost_ctx.get()
    if acc is None:
        return
    acc["prompt_tokens"] += prompt_tokens
    acc["completion_tokens"] += completion_tokens
    if model:
        breakdown = acc.setdefault("model_breakdown", {})
        entry = breakdown.setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0})
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
