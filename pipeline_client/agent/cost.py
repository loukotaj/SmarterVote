"""Token cost accounting for the agent pipeline."""

import re
from contextvars import ContextVar
from typing import Any, Dict, Optional

from shared.pipeline_config import PipelineRuntimeConfig

from .model_registry import MODEL_CATALOG, normalize_model_id

# ContextVar holds the live accumulator for the current run (async-safe).
# Shape: {"prompt_tokens": int, "completion_tokens": int,
#          "provider_cost_usd": float, "priced_calls": int, "unpriced_calls": int,
#          "model_breakdown": {model: {"prompt_tokens": int, "completion_tokens": int}}}
_cost_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("_cost_ctx", default=None)
_phase_ctx: ContextVar[str] = ContextVar("_phase_ctx", default="unattributed")

_DEFAULT_INPUT_PER_M = 2.50
_DEFAULT_OUTPUT_PER_M = 10.00


def phase_family(phase: str) -> str:
    """Collapse candidate/issue-specific phase labels into stable metric buckets."""
    normalized = str(phase or "unattributed").strip().lower().replace("_", "-")
    normalized = re.sub(r"^update-", "", normalized)
    if normalized.startswith("issue"):
        return "issues"
    for family in (
        "discovery",
        "images",
        "finance",
        "refinement",
        "polling",
        "forecast",
        "voter-resources",
        "review",
        "iteration",
    ):
        if normalized.startswith(family):
            return family.replace("-", "_")
    return normalized or "unattributed"


def set_current_phase(phase: str) -> None:
    _phase_ctx.set(phase_family(phase))


def _phase_entry(acc: Dict[str, Any]) -> Dict[str, Any]:
    return acc.setdefault("phase_breakdown", {}).setdefault(
        _phase_ctx.get(),
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "provider_cost_usd": 0.0,
            "llm_calls": 0,
            "search_calls": 0,
            "page_fetches": 0,
            "fetched_chars": 0,
        },
    )


def _phase_budget_baseline(acc: Dict[str, Any]) -> Dict[str, int]:
    """Return metrics already spent before this physical continuation pass."""
    baseline = acc.get("_phase_budget_baselines", {}).get(_phase_ctx.get(), {})
    return baseline if isinstance(baseline, dict) else {}


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
    phase = _phase_entry(acc)
    acc["prompt_tokens"] += prompt_tokens
    acc["completion_tokens"] += completion_tokens
    phase["prompt_tokens"] += prompt_tokens
    phase["completion_tokens"] += completion_tokens
    phase["llm_calls"] += 1
    if cost_usd is None:
        acc["unpriced_calls"] = acc.get("unpriced_calls", 0) + 1
    else:
        acc["provider_cost_usd"] = acc.get("provider_cost_usd", 0.0) + cost_usd
        acc["priced_calls"] = acc.get("priced_calls", 0) + 1
        phase["provider_cost_usd"] += cost_usd
    normalized_model = normalize_model_id(model) if model else None
    if normalized_model:
        breakdown = acc.setdefault("model_breakdown", {})
        entry = breakdown.setdefault(normalized_model, {"prompt_tokens": 0, "completion_tokens": 0})
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens


def record_context_metrics(
    *,
    estimated_input_tokens: int,
    context_window_tokens: int,
    deduplicated_results: int,
    compacted_results: int,
    truncated_results: int,
    dropped_tool_turns: int,
) -> None:
    """Record request context utilization and deterministic compaction work."""
    acc = _cost_ctx.get()
    if acc is None:
        return
    acc["context_requests"] = acc.get("context_requests", 0) + 1
    acc["max_estimated_context_tokens"] = max(
        acc.get("max_estimated_context_tokens", 0),
        estimated_input_tokens,
    )
    acc["max_context_window_tokens"] = max(
        acc.get("max_context_window_tokens", 0),
        context_window_tokens,
    )
    acc["context_deduplicated_results"] = max(
        acc.get("context_deduplicated_results", 0),
        deduplicated_results,
    )
    acc["context_compacted_results"] = acc.get("context_compacted_results", 0) + compacted_results
    acc["context_truncated_results"] = max(
        acc.get("context_truncated_results", 0),
        truncated_results,
    )
    acc["context_dropped_tool_turns"] = acc.get("context_dropped_tool_turns", 0) + dropped_tool_turns


def record_retry_metric(kind: str) -> None:
    """Increment a retry/deadline metric in the current run accumulator."""
    acc = _cost_ctx.get()
    if acc is None:
        return
    key = f"retry_{kind}"
    acc[key] = acc.get(key, 0) + 1


def reserve_search_call(provider: str) -> bool:
    """Atomically reserve one paid search call within the logical run ceiling."""
    acc = _cost_ctx.get()
    if acc is None:
        return True
    config = PipelineRuntimeConfig.from_env()
    used = int(acc.get("serper_calls", 0) or 0) + int(acc.get("searlo_calls", 0) or 0)
    phase = _phase_entry(acc)
    baseline = _phase_budget_baseline(acc)
    phase_used = int(phase.get("search_calls", 0)) - int(baseline.get("search_calls", 0))
    if used >= config.max_search_calls or phase_used >= config.max_phase_search_calls:
        acc["search_budget_blocked"] = int(acc.get("search_budget_blocked", 0) or 0) + 1
        phase["search_budget_blocked"] = int(phase.get("search_budget_blocked", 0) or 0) + 1
        return False
    key = f"{provider}_calls"
    acc[key] = int(acc.get(key, 0) or 0) + 1
    phase["search_calls"] += 1
    return True


def reserve_page_fetch() -> bool:
    """Reserve one uncached page fetch within logical-run and context ceilings."""
    acc = _cost_ctx.get()
    if acc is None:
        return True
    config = PipelineRuntimeConfig.from_env()
    phase = _phase_entry(acc)
    if (
        int(acc.get("page_fetches", 0) or 0) >= config.max_page_fetches
        or int(acc.get("fetched_chars", 0) or 0) >= config.max_fetched_chars
    ):
        acc["page_budget_blocked"] = int(acc.get("page_budget_blocked", 0) or 0) + 1
        phase["page_budget_blocked"] = int(phase.get("page_budget_blocked", 0) or 0) + 1
        return False
    acc["page_fetches"] = int(acc.get("page_fetches", 0) or 0) + 1
    phase["page_fetches"] += 1
    return True


def record_fetched_chars(count: int) -> None:
    acc = _cost_ctx.get()
    if acc is None:
        return
    count = max(0, int(count))
    acc["fetched_chars"] = int(acc.get("fetched_chars", 0) or 0) + count
    _phase_entry(acc)["fetched_chars"] += count


def total_token_budget_reached() -> bool:
    """Return whether prior completed model calls reached the logical run ceiling."""
    acc = _cost_ctx.get()
    if acc is None:
        return False
    used = int(acc.get("prompt_tokens", 0) or 0) + int(acc.get("completion_tokens", 0) or 0)
    config = PipelineRuntimeConfig.from_env()
    phase = _phase_entry(acc)
    baseline = _phase_budget_baseline(acc)
    phase_used = (
        int(phase.get("prompt_tokens", 0) or 0)
        + int(phase.get("completion_tokens", 0) or 0)
        - int(baseline.get("prompt_tokens", 0) or 0)
        - int(baseline.get("completion_tokens", 0) or 0)
    )
    return used >= config.max_total_tokens or phase_used >= config.max_phase_tokens


def record_token_budget_nudge() -> None:
    acc = _cost_ctx.get()
    if acc is not None:
        acc["token_budget_nudges"] = int(acc.get("token_budget_nudges", 0) or 0) + 1
