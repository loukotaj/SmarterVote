"""Pipeline-side adapter over the shared model catalog.

The models themselves — prices, capability scores, role assignments, escalation
edges — all live in :mod:`shared.model_catalog`, which is the one place any
service reads them from. This module only translates *run options* into a role
map: it knows about ``cheap_mode``, ``model_profile``, ``model_overrides`` and
the legacy per-role keyword arguments, none of which the shared catalog should
have to care about.

Import model names from here or from ``shared.model_catalog``; both resolve to
the same objects. Never write an OpenRouter model ID anywhere else.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from shared.model_catalog import (
    ADJUDICATOR_MODEL,
    DEFAULT_CHAMBER_FORECAST_MODEL,
    DEFAULT_RESEARCH_MODEL,
    DEFAULT_REVIEW_CLAUDE,
    DEFAULT_REVIEW_GEMINI,
    DEFAULT_REVIEW_GROK,
    FRONTIER_MODEL,
    LEGACY_MODEL_ALIASES,
    LEGACY_PROFILE_ALIASES,
    MODEL_CATALOG,
    MODEL_ESCALATION,
    MODEL_PROFILES,
    MODEL_ROLES,
    PREMIUM_RESEARCH_MODEL,
    PREMIUM_REVIEW_CLAUDE,
    PREMIUM_REVIEW_GEMINI,
    PREMIUM_REVIEW_GROK,
    PROFILE_DEFAULTS,
    SMALL_MODEL,
    ModelSpec,
    escalation_for,
    intelligence_of,
    normalize_model_id,
    normalize_profile_name,
    resolve_profile_models,
    spec_for,
)

__all__ = [
    "ADJUDICATOR_MODEL",
    "DEFAULT_CHAMBER_FORECAST_MODEL",
    "DEFAULT_RESEARCH_MODEL",
    "DEFAULT_REVIEW_CLAUDE",
    "DEFAULT_REVIEW_GEMINI",
    "DEFAULT_REVIEW_GROK",
    "FRONTIER_MODEL",
    "LEGACY_MODEL_ALIASES",
    "LEGACY_PROFILE_ALIASES",
    "MODEL_CATALOG",
    "MODEL_ESCALATION",
    "MODEL_PROFILES",
    "MODEL_ROLES",
    "PREMIUM_RESEARCH_MODEL",
    "PREMIUM_REVIEW_CLAUDE",
    "PREMIUM_REVIEW_GEMINI",
    "PREMIUM_REVIEW_GROK",
    "PROFILE_DEFAULTS",
    "SMALL_MODEL",
    "ModelSpec",
    "escalation_for",
    "intelligence_of",
    "normalize_model_id",
    "normalize_profile_name",
    "profile_from_options",
    "resolve_profile_models",
    "resolve_run_models",
    "spec_for",
]


def profile_from_options(options: Mapping[str, Any] | None = None, *, cheap_mode: Optional[bool] = None) -> str:
    """Resolve the model profile for a run.

    ``model_profile`` wins when it names a profile, old names included. Failing
    that, the historical ``cheap_mode`` boolean still decides: ``True`` is the
    default profile, ``False`` buys the premium one. An unset ``cheap_mode``
    used to mean the middle profile; there is no middle any more, and the tier
    it pointed at was worse *and* dearer than the default, so it now resolves to
    ``default`` — the same thing every caller that left it unset was trying to
    ask for.
    """
    options = options or {}
    raw_profile = options.get("model_profile")
    if isinstance(raw_profile, str) and raw_profile.strip():
        try:
            normalized = normalize_profile_name(raw_profile)
        except ValueError:
            normalized = None
        if normalized:
            return normalized
    if cheap_mode is None:
        cheap_mode = options.get("cheap_mode")
    return "premium" if cheap_mode is False else "default"


def resolve_run_models(
    options: Mapping[str, Any] | None = None,
    *,
    cheap_mode: Optional[bool] = None,
    research_model: Optional[str] = None,
    claude_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    grok_model: Optional[str] = None,
) -> Dict[str, str]:
    """Resolve the effective OpenRouter model for every agent role.

    Precedence, weakest first: profile defaults, then ``model_overrides``, then
    the legacy per-role keyword arguments. The returned mapping also carries the
    resolved profile name under ``"profile"``.
    """
    options = options or {}
    profile = profile_from_options(options, cheap_mode=cheap_mode)

    overrides = options.get("model_overrides")
    resolved = resolve_profile_models(profile, overrides=overrides if isinstance(overrides, Mapping) else None)

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
