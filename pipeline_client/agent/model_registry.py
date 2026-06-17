"""OpenRouter model catalog and legacy model compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

DEFAULT_MODEL = "openai/gpt-5.4"
CHEAP_MODEL = "openai/gpt-5.4-mini"
NANO_MODEL = "openai/gpt-5-nano"
DEEPSEEK_FLASH_MODEL = "deepseek/deepseek-v4-flash"

NEMOTRON_SUPER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
NEMOTRON_ULTRA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
LLAMA_3_3_70B_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEEPSEEK_R1_MODEL = "deepseek/deepseek-r1"

DEFAULT_CLAUDE_MODEL = "anthropic/claude-sonnet-4.6"
CHEAP_CLAUDE_MODEL = "anthropic/claude-haiku-4.5"

DEFAULT_GEMINI_MODEL = "google/gemini-3.1-pro-preview"
CHEAP_GEMINI_MODEL = "google/gemini-3.1-flash-lite"

DEFAULT_GROK_MODEL = "x-ai/grok-4.20"
CHEAP_GROK_MODEL = "x-ai/grok-4.3"

DEFAULT_ADMIN_CHAT_MODEL = NEMOTRON_ULTRA_MODEL

MODEL_PROFILES = {"economy", "balanced", "quality", "custom"}


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
    "deepseek/deepseek-v4-flash": ModelSpec("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", 0.09, 0.18, 1_048_576, 65_536),
    "nvidia/nemotron-3-super-120b-a12b": ModelSpec(
        "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super", 0.09, 0.45, 1_000_000
    ),
    "nvidia/nemotron-3-ultra-550b-a55b": ModelSpec(
        "nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra", 0.50, 2.20, 1_000_000, 16_384
    ),
    "meta-llama/llama-3.3-70b-instruct": ModelSpec(
        "meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct", 0.10, 0.32, 131_072, 16_384
    ),
    "deepseek/deepseek-r1": ModelSpec("deepseek/deepseek-r1", "DeepSeek R1", 0.70, 2.50, 163_840, 16_000),
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
    "nemotron-3-super": "nvidia/nemotron-3-super-120b-a12b",
    "nemotron-3-ultra": "nvidia/nemotron-3-ultra-550b-a55b",
    "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
    "deepseek-v3-0324": "deepseek/deepseek-chat-v3-0324",
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
    "gemini-3.5-flash": "google/gemini-3.5-flash",
    "deepseek-r1": "deepseek/deepseek-r1",
}

PROFILE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "economy": {
        "primary": DEEPSEEK_FLASH_MODEL,
        "small": NANO_MODEL,
        "review_claude": CHEAP_CLAUDE_MODEL,
        "review_gemini": CHEAP_GEMINI_MODEL,
        "review_grok": CHEAP_GROK_MODEL,
    },
    "balanced": {
        "primary": "google/gemini-2.5-flash",
        "small": LLAMA_3_3_70B_MODEL,
        "review_claude": CHEAP_CLAUDE_MODEL,
        "review_gemini": CHEAP_GEMINI_MODEL,
        "review_grok": CHEAP_GROK_MODEL,
    },
    "quality": {
        "primary": DEFAULT_MODEL,
        "small": DEFAULT_MODEL,
        "review_claude": DEFAULT_CLAUDE_MODEL,
        "review_gemini": DEFAULT_GEMINI_MODEL,
        "review_grok": DEFAULT_GROK_MODEL,
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
