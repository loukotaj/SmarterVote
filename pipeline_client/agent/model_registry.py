"""OpenRouter model catalog and legacy model compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from shared.pipeline_config import MODEL_PROFILES, MODEL_ROLES

# GPT-5.6 Luna. Replaced gpt-5.4-mini ($0.75/$4.50), which it beats on every
# axis: newer generation, 1.05M context instead of 400K, and 7.5x cheaper.
CHEAP_MODEL = "openai/gpt-5.6-luna"
MID_MODEL = "openai/gpt-5.6-terra"
# Escalation target when a cheap model stalls (see CHEAP_TO_DEFAULT_MODEL_FALLBACK).
# It must be genuinely stronger than CHEAP_MODEL or escalation buys nothing —
# pointing it at another economy-tier model would make the fallback a lateral
# move. Same family as CHEAP_MODEL so prompt behaviour stays consistent.
DEFAULT_MODEL = MID_MODEL
# Retained for explicit opt-in only. gpt-5-nano spends ~384 reasoning tokens
# before emitting any content — measured, not estimated — so a small task costs
# ~409 output tokens against Luna's ~48 for the same answer. At $0.40/M versus
# Luna's $0.60/M that makes nano roughly 5.7x *more* expensive in practice, and
# under a tight max_tokens it returns finish_reason="length" with empty content.
NANO_MODEL = "openai/gpt-5-nano"
DEEPSEEK_FLASH_MODEL = "deepseek/deepseek-v4-flash-0731"
DEEPSEEK_PRO_MODEL = "deepseek/deepseek-v4-pro"

NEMOTRON_SUPER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
NEMOTRON_ULTRA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

DEFAULT_CLAUDE_MODEL = "anthropic/claude-sonnet-5"
CHEAP_CLAUDE_MODEL = "anthropic/claude-haiku-4.5"

DEFAULT_GEMINI_MODEL = "google/gemini-3.1-pro-preview"
CHEAP_GEMINI_MODEL = "google/gemini-3.1-flash-lite"

DEFAULT_GROK_MODEL = "x-ai/grok-4.20"
CHEAP_GROK_MODEL = "x-ai/grok-4.3"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    input_per_m: float
    output_per_m: float
    context_window_tokens: int
    max_completion_tokens: Optional[int] = None


MODEL_CATALOG: Dict[str, ModelSpec] = {
    "openai/gpt-5.4": ModelSpec("openai/gpt-5.4", "GPT-5.4", 2.50, 15.00, 1_050_000, 128_000),
    "openai/gpt-5.4-mini": ModelSpec("openai/gpt-5.4-mini", "GPT-5.4 Mini", 0.75, 4.50, 400_000, 128_000),
    "openai/gpt-5-nano": ModelSpec("openai/gpt-5-nano", "GPT-5 Nano", 0.05, 0.40, 400_000),
    "openai/gpt-5.6-luna": ModelSpec("openai/gpt-5.6-luna", "GPT-5.6 Luna", 0.10, 0.60, 1_050_000, 128_000),
    "openai/gpt-5.6-terra": ModelSpec("openai/gpt-5.6-terra", "GPT-5.6 Terra", 1.00, 6.00, 1_050_000, 128_000),
    "openai/gpt-5.6-sol": ModelSpec("openai/gpt-5.6-sol", "GPT-5.6 Sol", 5.00, 30.00, 1_050_000, 128_000),
    "anthropic/claude-sonnet-5": ModelSpec("anthropic/claude-sonnet-5", "Claude Sonnet 5", 2.00, 10.00, 1_000_000, 128_000),
    "anthropic/claude-sonnet-4.6": ModelSpec(
        "anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6", 3.00, 15.00, 1_000_000, 128_000
    ),
    "anthropic/claude-haiku-4.5": ModelSpec("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", 1.00, 5.00, 200_000, 64_000),
    "google/gemini-3.1-pro-preview": ModelSpec(
        "google/gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview", 2.00, 12.00, 1_048_576, 65_536
    ),
    "google/gemini-3.1-flash-lite-preview": ModelSpec(
        "google/gemini-3.1-flash-lite-preview", "Gemini 3.1 Flash Lite Preview", 0.25, 1.50, 1_048_576, 65_536
    ),
    "google/gemini-3-flash-preview": ModelSpec(
        "google/gemini-3-flash-preview", "Gemini 3 Flash Preview", 0.50, 3.00, 1_048_576, 65_536
    ),
    "x-ai/grok-4.20": ModelSpec("x-ai/grok-4.20", "Grok 4.20", 1.25, 2.50, 2_000_000),
    "x-ai/grok-4.3": ModelSpec("x-ai/grok-4.3", "Grok 4.3", 1.25, 2.50, 1_000_000),
    "deepseek/deepseek-v4-flash": ModelSpec("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", 0.14, 0.28, 1_048_576, 65_536),
    "deepseek/deepseek-v4-flash-0731": ModelSpec(
        "deepseek/deepseek-v4-flash-0731", "DeepSeek V4 Flash (07-31)", 0.09, 0.18, 1_048_576, 65_536
    ),
    "deepseek/deepseek-v4-pro": ModelSpec("deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", 0.435, 0.87, 1_048_576, 65_536),
    "nvidia/nemotron-3-super-120b-a12b": ModelSpec(
        "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super", 0.085, 0.40, 1_000_000
    ),
    "nvidia/nemotron-3-ultra-550b-a55b": ModelSpec(
        "nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra", 0.60, 3.60, 512_288, 16_384
    ),
    # --- Additional confirmed models ---
    "deepseek/deepseek-chat-v3-0324": ModelSpec(
        "deepseek/deepseek-chat-v3-0324", "DeepSeek V3 0324", 0.20, 0.77, 163_840, 65_536
    ),
    "google/gemini-2.5-flash": ModelSpec("google/gemini-2.5-flash", "Gemini 2.5 Flash", 0.30, 2.50, 1_048_576, 65_536),
    # GA version of Flash Lite (non-preview)
    "google/gemini-3.1-flash-lite": ModelSpec(
        "google/gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", 0.25, 1.50, 1_048_576, 65_536
    ),
    # Near-frontier quality at Flash speed; note: output is expensive
    "google/gemini-3.5-flash": ModelSpec("google/gemini-3.5-flash", "Gemini 3.5 Flash", 1.50, 9.00, 1_048_576, 65_536),
}

LEGACY_MODEL_ALIASES: Dict[str, str] = {
    "gpt-5.4": "openai/gpt-5.4",
    "gpt-5.4-mini": "openai/gpt-5.4-mini",
    "gpt-5-nano": "openai/gpt-5-nano",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "deepseek-v4-flash-0731": "deepseek/deepseek-v4-flash-0731",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    "claude-3-5-sonnet-20241022": "anthropic/claude-sonnet-4.6",
    "claude-3-haiku-20240307": "anthropic/claude-haiku-4.5",
    "gemini-3.1-pro-preview": "google/gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite",
    "gemini-3-flash-preview": "google/gemini-3-flash-preview",
    "grok-4.20-0309-reasoning": "x-ai/grok-4.20",
    "grok-4-1-fast-non-reasoning": "x-ai/grok-4.3",
    "grok-3-mini": "x-ai/grok-4.3",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "nemotron-3-super": "nvidia/nemotron-3-super-120b-a12b",
    "nemotron-3-ultra": "nvidia/nemotron-3-ultra-550b-a55b",
    "deepseek-v3-0324": "deepseek/deepseek-chat-v3-0324",
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
    "gemini-3.5-flash": "google/gemini-3.5-flash",
}

# Roster sync/verify decides which people are current candidates — a reasoning
# task where the economy primary (DeepSeek Flash) has under-performed (kept
# retired ex-incumbents / prior-cycle candidates). These are only ~1-2 calls per
# race, so a stronger instruction-follower here is cheap insurance. Flash Lite
# replaced Gemini 2.5 Flash: two generations newer and cheaper on both input and
# output ($0.25/$1.50 against $0.30/$2.50).
ROSTER_MODEL = CHEAP_GEMINI_MODEL

# Every role in every profile sits on a current-generation model. Prices are per
# million tokens, verified against OpenRouter's live model list rather than
# recalled, since Luna alone repriced twice in July.
PROFILE_DEFAULTS: Dict[str, Dict[str, str]] = {
    # The default for MCP queueing (cheap_mode=True). Cheapest capable model at
    # each step, not cheapest headline price — see NANO_MODEL on why the nominally
    # cheaper option costs more once reasoning tokens are counted.
    "economy": {
        "primary": DEEPSEEK_FLASH_MODEL,  # $0.09/$0.18, 1M ctx
        "small": CHEAP_MODEL,  # $0.10/$0.60 — replaced nano, ~5.7x cheaper in practice
        "roster": ROSTER_MODEL,  # $0.25/$1.50
        "review_claude": CHEAP_CLAUDE_MODEL,  # $1.00/$5.00
        "review_gemini": CHEAP_GEMINI_MODEL,  # $0.25/$1.50
        "review_grok": CHEAP_GROK_MODEL,  # $1.25/$2.50
    },
    "balanced": {
        "primary": CHEAP_GEMINI_MODEL,  # $0.25/$1.50
        "small": CHEAP_MODEL,  # $0.10/$0.60
        "roster": ROSTER_MODEL,
        "review_claude": CHEAP_CLAUDE_MODEL,
        "review_gemini": CHEAP_GEMINI_MODEL,
        "review_grok": CHEAP_GROK_MODEL,
    },
    # High quality. Research and roster move to the current mid tier, and the
    # three reviewers to their current flagships — review is where quality is
    # actually decided, and it runs a handful of times per race rather than once
    # per candidate/issue pair.
    "quality": {
        "primary": MID_MODEL,  # $1.00/$6.00, 1.05M ctx
        "small": CHEAP_MODEL,  # $0.10/$0.60 — sub-agent work does not need the mid tier
        "roster": MID_MODEL,
        "review_claude": DEFAULT_CLAUDE_MODEL,  # Sonnet 5, $2.00/$10.00
        "review_gemini": DEFAULT_GEMINI_MODEL,  # Gemini 3.1 Pro, $2.00/$12.00
        "review_grok": DEFAULT_GROK_MODEL,  # Grok 4.20, $1.25/$2.50
    },
}


def normalize_model_id(model: Optional[str]) -> Optional[str]:
    """Return the OpenRouter model ID for a legacy or canonical model string."""
    if model is None:
        return None
    value = str(model).strip()
    if not value:
        return None
    return LEGACY_MODEL_ALIASES.get(value, value)


def profile_from_options(options: Mapping[str, Any] | None = None, *, cheap_mode: Optional[bool] = None) -> str:
    """Resolve the model profile, preserving old cheap_mode semantics."""
    options = options or {}
    raw_profile = options.get("model_profile")
    if isinstance(raw_profile, str) and raw_profile in MODEL_PROFILES:
        return raw_profile
    if cheap_mode is None:
        cheap_mode = options.get("cheap_mode")
    if cheap_mode is True:
        return "economy"
    if cheap_mode is False:
        return "quality"
    return "balanced"


def resolve_run_models(
    options: Mapping[str, Any] | None = None,
    *,
    cheap_mode: Optional[bool] = None,
    research_model: Optional[str] = None,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
) -> Dict[str, str]:
    """Resolve effective OpenRouter models for every agent role."""
    options = options or {}
    profile = profile_from_options(options, cheap_mode=cheap_mode)
    base_profile = "balanced" if profile == "custom" else profile
    resolved = dict(PROFILE_DEFAULTS[base_profile])

    overrides = options.get("model_overrides")
    if isinstance(overrides, Mapping):
        for key, value in overrides.items():
            if str(key) not in MODEL_ROLES:
                raise ValueError(f"Unknown model_overrides role: {key}")
            normalized = normalize_model_id(value if isinstance(value, str) else None)
            if normalized:
                resolved[str(key)] = normalized

    legacy_overrides = {
        "primary": research_model or options.get("research_model"),
        "review_claude": claude_model or options.get("claude_model"),
        "review_gemini": gemini_model or options.get("gemini_model"),
        "review_grok": grok_model or options.get("grok_model"),
    }
    for role, value in legacy_overrides.items():
        normalized = normalize_model_id(value if isinstance(value, str) else None)
        if normalized:
            resolved[role] = normalized

    resolved["profile"] = profile
    return resolved
