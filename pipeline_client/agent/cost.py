"""Token cost accounting for the agent pipeline."""

from contextvars import ContextVar
from typing import Any, Dict, Optional

from .model_registry import MODEL_CATALOG, normalize_model_id

# ContextVar holds the live accumulator for the current run (async-safe).
# Shape: {"prompt_tokens": int, "completion_tokens": int,
#          "provider_cost_usd": float, "priced_calls": int, "unpriced_calls": int,
#          "model_breakdown": {model: {"prompt_tokens": int, "completion_tokens": int}}}
_cost_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("_cost_ctx", default=None)

_DEFAULT_INPUT_PER_M = 2.50
_DEFAULT_OUTPUT_PER_M = 10.00


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated USD cost for a single model call."""
    spec = MODEL_CATALOG.get(normalize_model_id(model) or model)
    input_per_m = spec.input_per_m if spec else _DEFAULT_INPUT_PER_M
    output_per_m = spec.output_per_m if spec else _DEFAULT_OUTPUT_PER_M
    return prompt_tokens / 1_000_000 * input_per_m + completion_tokens / 1_000_000 * output_per_m


def accumulate(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "",
    *,
    cost_usd: Optional[float] = None,
) -> None:
    """Add token counts and the provider-reported charge to the live run."""
    acc = _cost_ctx.get()
    if acc is None:
        return
    acc["prompt_tokens"] += prompt_tokens
    acc["completion_tokens"] += completion_tokens
    if cost_usd is None:
        acc["unpriced_calls"] = acc.get("unpriced_calls", 0) + 1
    else:
        acc["provider_cost_usd"] = acc.get("provider_cost_usd", 0.0) + cost_usd
        acc["priced_calls"] = acc.get("priced_calls", 0) + 1
    normalized_model = normalize_model_id(model) if model else None
    if normalized_model:
        breakdown = acc.setdefault("model_breakdown", {})
        entry = breakdown.setdefault(normalized_model, {"prompt_tokens": 0, "completion_tokens": 0})
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
