"""The single source of truth for every model SmarterVote can run.

Everything that picks a model — the research agent, the roster adjudicator, the
review panel, the chamber-forecast endpoint, the MCP tools — resolves it from
here. Nothing else may hardcode an OpenRouter model ID. Four separate copies of
the chamber-forecast model had already drifted apart (two of them to a model
that was both older *and* dearer on output) before this module existed, so the
rule is deliberately absolute: one literal, one place.

It lives in ``shared/`` rather than under ``pipeline_client/agent/`` because
``services/races-api`` needs it too and only ``shared/`` is copied into that
container.

Three kinds of fact live here, and they are maintained differently:

* **Prices and context windows** are the provider's facts. They drift weekly and
  are verified against OpenRouter's live model list by
  ``scripts/check_model_catalog.py``. Never edit them from memory.
* **Intelligence index** is our capability yardstick — Artificial Analysis
  Intelligence Index v4.1, captured 2026-08-07. Nothing can verify it
  automatically, so it is written down explicitly and cited. It exists because
  price is *not* a proxy for capability: nemotron-3-ultra cost 6.7x more per
  input token than deepseek-v4-flash-0731 while scoring 12 points *lower*, and
  the guard's price-based escalation check waved that through for months.
* **Role assignments** are our judgment, argued in comments at each choice.

Adding a model? Add it to :data:`MODEL_CATALOG` with a real intelligence score
and run ``python scripts/check_model_catalog.py`` before committing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

# ---------------------------------------------------------------------------
# Roles and profiles
# ---------------------------------------------------------------------------

#: Every distinct job a model is chosen for. ``model_overrides`` is validated
#: against this set.
MODEL_ROLES = frozenset({"primary", "small", "roster", "review_claude", "review_gemini", "review_grok"})

#: Two real profiles, plus ``custom`` for a run that overrides roles by hand.
#:
#: There used to be three. ``balanced`` sat between ``economy`` and ``quality``
#: and was strictly dominated by both: its only difference from ``economy`` was a
#: primary model scoring 25.0 against economy's 49.9 while costing 2.8x more per
#: input token. Nobody could have wanted it. Two tiers — the one you run, and
#: the one you pay for — is the whole useful range.
MODEL_PROFILES = frozenset({"default", "premium", "custom"})

#: Runs queued before the two-profile consolidation still carry the old names,
#: and so do stored run records the admin UI replays. Map them forward.
#: ``balanced`` folds into ``default`` because that is what it should always
#: have been.
LEGACY_PROFILE_ALIASES: Dict[str, str] = {
    "economy": "default",
    "balanced": "default",
    "quality": "premium",
}


@dataclass(frozen=True)
class ModelSpec:
    """One model, priced per million tokens.

    ``intelligence`` is the Artificial Analysis Intelligence Index v4.1 score.
    It is the field the escalation guard reasons about — see the module
    docstring for why output price cannot stand in for it.
    """

    id: str
    label: str
    input_per_m: float
    output_per_m: float
    #: Price of a cached input-token read. ``None`` means the provider does not
    #: offer cache reads through OpenRouter.
    cached_input_per_m: Optional[float]
    context_window_tokens: int
    intelligence: float
    max_completion_tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Prompt caching — measured, 2026-08-07
# ---------------------------------------------------------------------------
#
# The latest 250 production metric records are 31.4:1 input:output
# (170.4M:5.4M, measured 2026-08-13), so cache behaviour matters more than any
# other price on this page. It is also entirely provider-specific and not
# something you can read off the OpenRouter price list, so it was measured
# directly: identical 5.7k-token prefix, sent twice, with and without an
# explicit `cache_control` breakpoint.
#
#   openai      implicit, works.   Luna: $0.00072 cold -> $0.000077 warm (10.6x)
#   deepseek    implicit, works.   Flash: $0.00082 cold -> $0.00012 warm (7x)
#   x-ai        implicit, works.   Grok 4.3 warm: $0.0027
#   google      implicit: NONE.    Explicit `cache_control`: 2.6x cheaper
#   anthropic   implicit: NONE.    Explicit: 8.2x warm, but +24% on a cold write
#
# **Do not add `cache_control` to x-ai requests.** It does not merely fail to
# help — it *suppresses* Grok's implicit caching (cached tokens fell from 5888
# to 192) and made the same call 3.3x more expensive. That is the trap this
# note exists to prevent.
#
# Google and Anthropic would benefit from an explicit breakpoint, but only over
# a stable prefix worth caching. The one prefix we re-send to them is
# ``REVIEW_SYSTEM`` at ~740 tokens — below Anthropic's 2048-token minimum, so
# it would never engage, while the large part of a review prompt (the race
# packet) changes on every call by design. So there is no caching code in the
# pipeline, deliberately.
#
# This used to matter much more: the roster role ran on Gemini, which caches
# nothing implicitly, and it was 36% of the bill. Moving roster onto DeepSeek
# closed that gap without any caching code at all. Realized discount across
# production runs before the move was 4.2%.


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------
#
# Curated, not exhaustive: OpenRouter serves 339 models and we keep the ones
# that are the best answer to some question we actually ask. Every entry is
# reachable through a profile role or an explicit `model_overrides` request.
#
# Prices, context windows, and completion limits verified against OpenRouter
# live 2026-08-13.

MODEL_CATALOG: Dict[str, ModelSpec] = {
    # --- OpenAI: GPT-5.6 family (2026-07-09) -------------------------------
    # One generation, three sizes, identical 1.05M context. Luna is the
    # cheapest model in the catalog that still scores above 50, which makes it
    # the workhorse for bounded judgment calls.
    "openai/gpt-5.6-luna": ModelSpec("openai/gpt-5.6-luna", "GPT-5.6 Luna", 0.10, 0.60, 0.01, 1_050_000, 51.2, 128_000),
    "openai/gpt-5.6-terra": ModelSpec("openai/gpt-5.6-terra", "GPT-5.6 Terra", 1.00, 6.00, 0.10, 1_050_000, 55.0, 128_000),
    "openai/gpt-5.6-sol": ModelSpec("openai/gpt-5.6-sol", "GPT-5.6 Sol", 5.00, 30.00, 0.50, 1_050_000, 58.9, 128_000),
    # --- DeepSeek ----------------------------------------------------------
    # The 0731 build is the reason the default profile is cheap. It scores
    # within 1.3 points of Luna at 9/100ths the output price, and its gains
    # over the original V4 Flash were concentrated exactly where we use it:
    # agentic tool loops (GDPval-AA 1189 -> 1559 Elo, Terminal-Bench +17pts).
    # Pinned to the dated snapshot; the floating `deepseek-v4-flash` alias is
    # a different, older, dearer model.
    "deepseek/deepseek-v4-flash-0731": ModelSpec(
        "deepseek/deepseek-v4-flash-0731", "DeepSeek V4 Flash (07-31)", 0.08, 0.18, 0.016, 1_048_576, 49.9, 384_000
    ),
    # Confusingly, "Pro" scores *below* the newer Flash (44.3 against 49.9).
    # Kept only so an explicit override resolves to a real price.
    "deepseek/deepseek-v4-pro": ModelSpec(
        "deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", 1.168, 2.336, 0.09855, 1_048_576, 44.3, 393_216
    ),
    # --- Google ------------------------------------------------------------
    "google/gemini-3.1-flash-lite": ModelSpec(
        "google/gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", 0.25, 1.50, 0.025, 1_048_576, 25.0, 65_536
    ),
    "google/gemini-3.5-flash-lite": ModelSpec(
        "google/gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", 0.30, 2.50, 0.03, 1_048_576, 36.5, 65_536
    ),
    "google/gemini-3.6-flash": ModelSpec(
        "google/gemini-3.6-flash", "Gemini 3.6 Flash", 1.50, 7.50, 0.15, 1_048_576, 50.1, 65_536
    ),
    # --- Anthropic ---------------------------------------------------------
    # Haiku 4.5 is old (2025-10-15) and weak, and it stays because it is the
    # only sub-$2 Anthropic model OpenRouter serves. The review panel wants
    # three *different* houses more than it wants three strong models, and
    # dropping the Anthropic seat entirely would cost more than Haiku does.
    "anthropic/claude-haiku-4.5": ModelSpec(
        "anthropic/claude-haiku-4.5", "Claude Haiku 4.5", 1.00, 5.00, 0.10, 200_000, 24.0, 64_000
    ),
    "anthropic/claude-sonnet-5": ModelSpec(
        "anthropic/claude-sonnet-5", "Claude Sonnet 5", 2.00, 10.00, 0.20, 1_000_000, 53.4, 128_000
    ),
    "anthropic/claude-opus-5": ModelSpec(
        "anthropic/claude-opus-5", "Claude Opus 5", 5.00, 25.00, 0.50, 1_000_000, 60.7, 128_000
    ),
    # --- xAI ---------------------------------------------------------------
    # Grok version strings sort by decimal, not integer: 4.20 (2026-03-31) is
    # *older* than 4.3 (2026-04-30), which is older than 4.5 (2026-07-08).
    # Reading them the other way once put the premium reviewer on an older
    # model than the default one. Release dates decide, never string order.
    "x-ai/grok-4.3": ModelSpec("x-ai/grok-4.3", "Grok 4.3", 1.25, 2.50, 0.20, 1_000_000, 37.6),
    "x-ai/grok-4.5": ModelSpec("x-ai/grok-4.5", "Grok 4.5", 2.00, 6.00, 0.30, 500_000, 53.8),
}


# ---------------------------------------------------------------------------
# Named roles
# ---------------------------------------------------------------------------

#: Research and roster work for the default profile. Huge prompts, small
#: completions — measured at 31.4:1 input:output across the latest 250
#: production metric records — so the input price is what matters and
#: DeepSeek's is the lowest above 45 index.
DEFAULT_RESEARCH_MODEL = "deepseek/deepseek-v4-flash-0731"

#: Same jobs under ``premium``. Terra is the cheapest model that genuinely beats
#: the default research model (55.0 against 49.9); Luna's +1.3 would not be an
#: upgrade worth a profile switch.
PREMIUM_RESEARCH_MODEL = "openai/gpt-5.6-terra"

#: Bounded sub-agent work and the roster adjudication gate, in *both* profiles.
#: Deliberately not the research model — see :data:`ADJUDICATOR_MODEL`.
SMALL_MODEL = "openai/gpt-5.6-luna"

#: Ceiling for escalation. Nothing routes here by default.
FRONTIER_MODEL = "openai/gpt-5.6-sol"

DEFAULT_REVIEW_CLAUDE = "anthropic/claude-haiku-4.5"
DEFAULT_REVIEW_GEMINI = "google/gemini-3.5-flash-lite"
DEFAULT_REVIEW_GROK = "x-ai/grok-4.3"

PREMIUM_REVIEW_CLAUDE = "anthropic/claude-sonnet-5"
PREMIUM_REVIEW_GEMINI = "google/gemini-3.6-flash"
PREMIUM_REVIEW_GROK = "x-ai/grok-4.5"

#: The fail-closed reading-comprehension gate in front of every roster edit.
#:
#: Pinned rather than profile-resolved: a floating choice would let a provider
#: upgrade move a publish gate with no commit to point at.
#:
#: It must differ from the `primary` and `roster` models of **every** profile.
#: The gate's whole claim to independence is that the model producing the
#: evidence is not the model judging it, and roster edits are made from both
#: roster-phase loops (roster model) and metadata/refinement loops (primary
#: model). Luna satisfies that against both DeepSeek and Terra, accepts
#: ``temperature=0``, and returns well-formed JSON — all three verified against
#: the live API. ``scripts/check_model_catalog.py`` enforces the separation.
ADJUDICATOR_MODEL = SMALL_MODEL

#: Strong, independent second look used only when every ordinary completeness
#: judgment rejects a structurally valid roster-evidence bundle.
ROSTER_COMPLETENESS_REVIEW_MODEL = "anthropic/claude-opus-5"

#: Chamber-forecast narratives: a handful of long-context calls over every
#: published race summary, run by hand from the admin UI rather than per race.
#: Volume is negligible, so this takes the strong Gemini rather than the cheap
#: one. Imported by the races-api endpoint and the MCP tool — never re-typed.
DEFAULT_CHAMBER_FORECAST_MODEL = PREMIUM_REVIEW_GEMINI


PROFILE_DEFAULTS: Dict[str, Dict[str, str]] = {
    # What every queued race runs unless someone pays for more.
    "default": {
        "primary": DEFAULT_RESEARCH_MODEL,
        "small": SMALL_MODEL,
        # Roster verification decides who is on the ballot, so it used to get a
        # different, supposedly stronger model than research. That reasoning
        # inverted when DeepSeek shipped 0731: the "stronger" roster model
        # (gemini-3.5-flash-lite) scores 36.5 against research's 49.9, while
        # costing 3.3x more per input token. It was the single largest line in
        # the bill — 36% of LLM spend on 21% of the tokens — and being weak in a
        # long tool loop, it tripped the tool-error escalation that accounted
        # for another 26%. Both problems end here.
        "roster": DEFAULT_RESEARCH_MODEL,
        "review_claude": DEFAULT_REVIEW_CLAUDE,
        "review_gemini": DEFAULT_REVIEW_GEMINI,
        "review_grok": DEFAULT_REVIEW_GROK,
        # Note: `roster` matching `primary` is a coincidence of the current
        # catalog, not a merge of the two roles. It stays a separate role so a
        # roster regression is a one-line fix, and so `premium` can differ.
    },
    # Research and roster move up a real tier and all three reviewers go to
    # their flagships. Review is where quality is actually decided and it runs a
    # handful of times per race rather than once per candidate/issue pair.
    "premium": {
        "primary": PREMIUM_RESEARCH_MODEL,
        "small": SMALL_MODEL,
        "roster": PREMIUM_RESEARCH_MODEL,
        "review_claude": PREMIUM_REVIEW_CLAUDE,
        "review_gemini": PREMIUM_REVIEW_GEMINI,
        "review_grok": PREMIUM_REVIEW_GROK,
    },
}


#: Where a model goes when it stalls: repeated JSON-parse failures, blocked tool
#: edits, or the final-synthesis turns of a long agent loop.
#:
#: Every edge must climb the intelligence index. That sounds obvious and was not
#: true: the previous map sent deepseek-v4-flash-0731 (49.9) to
#: nemotron-3-ultra (37.8) at 6.7x the input price, and because
#: ``check_model_catalog.py`` compared *output price* rather than capability, it
#: reported the downgrade as a healthy escalation. The guard now compares
#: :attr:`ModelSpec.intelligence`, so this cannot come back.
#:
#: Edges stay inside one provider family wherever possible so prompt behaviour
#: does not shift mid-loop.
MODEL_ESCALATION: Dict[str, str] = {
    DEFAULT_RESEARCH_MODEL: PREMIUM_RESEARCH_MODEL,  # 49.9 -> 55.0
    SMALL_MODEL: PREMIUM_RESEARCH_MODEL,  # 51.2 -> 55.0
    PREMIUM_RESEARCH_MODEL: FRONTIER_MODEL,  # 55.0 -> 58.9
    DEFAULT_REVIEW_CLAUDE: PREMIUM_REVIEW_CLAUDE,  # 24.0 -> 53.4
    DEFAULT_REVIEW_GEMINI: PREMIUM_REVIEW_GEMINI,  # 36.5 -> 50.1
    DEFAULT_REVIEW_GROK: PREMIUM_REVIEW_GROK,  # 37.6 -> 53.8
}


#: Old model strings that still appear in stored run options and race records.
#: Every value must be a live catalog key, so replaying an old run resolves to
#: something real rather than falling back to a default price.
LEGACY_MODEL_ALIASES: Dict[str, str] = {
    # Bare names for models still in the catalog.
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "deepseek-v4-flash-0731": "deepseek/deepseek-v4-flash-0731",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "claude-opus-5": "anthropic/claude-opus-5",
    "gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite": "google/gemini-3.5-flash-lite",
    "gemini-3.6-flash": "google/gemini-3.6-flash",
    "grok-4.3": "x-ai/grok-4.3",
    "grok-4.5": "x-ai/grok-4.5",
    # Retired models, mapped to their nearest current equivalent so historical
    # runs still price and re-run sensibly.
    "openai/gpt-5.4": "openai/gpt-5.6-terra",
    "openai/gpt-5.4-mini": "openai/gpt-5.6-luna",
    "openai/gpt-5-nano": "openai/gpt-5.6-luna",
    "gpt-5.4": "openai/gpt-5.6-terra",
    "gpt-5.4-mini": "openai/gpt-5.6-luna",
    "gpt-5-nano": "openai/gpt-5.6-luna",
    "deepseek/deepseek-v4-flash": "deepseek/deepseek-v4-flash-0731",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-chat-v3-0324": "deepseek/deepseek-v4-flash-0731",
    "deepseek-v3-0324": "deepseek/deepseek-v4-flash-0731",
    "anthropic/claude-sonnet-4.6": "anthropic/claude-sonnet-5",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-5",
    "claude-3-5-sonnet-20241022": "anthropic/claude-sonnet-5",
    "claude-3-haiku-20240307": "anthropic/claude-haiku-4.5",
    "google/gemini-3.1-pro-preview": "google/gemini-3.6-flash",
    "gemini-3.1-pro-preview": "google/gemini-3.6-flash",
    "google/gemini-3-flash-preview": "google/gemini-3.6-flash",
    "gemini-3-flash-preview": "google/gemini-3.6-flash",
    "google/gemini-3.5-flash": "google/gemini-3.6-flash",
    "gemini-3.5-flash": "google/gemini-3.6-flash",
    "google/gemini-2.5-flash": "google/gemini-3.5-flash-lite",
    "gemini-2.5-flash": "google/gemini-3.5-flash-lite",
    "google/gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite",
    "x-ai/grok-4.20": "x-ai/grok-4.3",
    "grok-4.20-0309-reasoning": "x-ai/grok-4.3",
    "grok-4-1-fast-non-reasoning": "x-ai/grok-4.3",
    "grok-3-mini": "x-ai/grok-4.3",
    # Nemotron was only ever an escalation target, and a downgrade at that.
    "nvidia/nemotron-3-super-120b-a12b": "deepseek/deepseek-v4-flash-0731",
    "nvidia/nemotron-3-ultra-550b-a55b": "openai/gpt-5.6-terra",
    "nemotron-3-super": "deepseek/deepseek-v4-flash-0731",
    "nemotron-3-ultra": "openai/gpt-5.6-terra",
}


#: Display names for models we no longer run but that still appear in stored run
#: records. A historical run must render as the model it actually used, so these
#: are labels only — never resolve a *new* run onto one of these. Anything with
#: a current equivalent is in :data:`LEGACY_MODEL_ALIASES` as well; the two serve
#: different purposes and both are needed.
RETIRED_MODEL_LABELS: Dict[str, str] = {
    "openai/gpt-5.4": "GPT-5.4",
    "openai/gpt-5.4-mini": "GPT-5.4 Mini",
    "openai/gpt-5-nano": "GPT-5 Nano",
    "anthropic/claude-sonnet-4.6": "Claude Sonnet 4.6",
    "google/gemini-3-flash-preview": "Gemini 3 Flash (Preview)",
    "google/gemini-3.1-pro-preview": "Gemini 3.1 Pro (Preview)",
    "google/gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite (Preview)",
    "google/gemini-3.5-flash": "Gemini 3.5 Flash",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash",
    "x-ai/grok-4.20": "Grok 4.20",
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek/deepseek-chat-v3-0324": "DeepSeek V3 0324",
    "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super",
    "nvidia/nemotron-3-ultra-550b-a55b": "Nemotron 3 Ultra",
}


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def normalize_model_id(model: Optional[str]) -> Optional[str]:
    """Return the OpenRouter model ID for a legacy or canonical model string."""
    if model is None:
        return None
    value = str(model).strip()
    if not value:
        return None
    return LEGACY_MODEL_ALIASES.get(value, value)


def normalize_profile_name(profile: Optional[str]) -> Optional[str]:
    """Map a profile name — current or retired — onto a current one.

    Returns ``None`` for ``None`` so callers can distinguish "not requested"
    from "requested and invalid"; raises for a name that was never valid.
    """
    if profile is None:
        return None
    value = str(profile).strip().lower()
    if not value:
        return None
    value = LEGACY_PROFILE_ALIASES.get(value, value)
    if value not in MODEL_PROFILES:
        raise ValueError("model_profile must be one of: default, premium, custom")
    return value


def label_for(model: Optional[str]) -> str:
    """Return a display name for any model string we have ever run.

    Current models come from the catalog, retired ones from
    :data:`RETIRED_MODEL_LABELS`. A historical run renders as the model it
    actually used, never as whatever replaced it.
    """
    value = str(model or "").strip()
    if not value:
        return ""
    spec = MODEL_CATALOG.get(value)
    if spec:
        return spec.label
    retired = RETIRED_MODEL_LABELS.get(value)
    if retired:
        return retired
    aliased = LEGACY_MODEL_ALIASES.get(value)
    if aliased and aliased in MODEL_CATALOG:
        return MODEL_CATALOG[aliased].label
    return value


def spec_for(model: Optional[str]) -> Optional[ModelSpec]:
    """Return the catalog entry for a model string, or ``None`` if unknown."""
    normalized = normalize_model_id(model)
    return MODEL_CATALOG.get(normalized) if normalized else None


def intelligence_of(model: Optional[str]) -> Optional[float]:
    """Return a model's intelligence index, or ``None`` if it is not catalogued."""
    spec = spec_for(model)
    return spec.intelligence if spec else None


def escalation_for(model: Optional[str]) -> Optional[str]:
    """Return the model to climb to when *model* stalls, if there is one."""
    normalized = normalize_model_id(model)
    return MODEL_ESCALATION.get(normalized) if normalized else None


def resolve_profile_models(
    profile: Optional[str] = None,
    *,
    overrides: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    """Return ``{role: model_id}`` for *profile*, with per-role overrides applied.

    ``custom`` resolves from ``default`` and expects overrides to do the rest.
    """
    resolved_profile = normalize_profile_name(profile) or "default"
    base = "default" if resolved_profile == "custom" else resolved_profile
    models = dict(PROFILE_DEFAULTS[base])
    for role, value in (overrides or {}).items():
        if str(role) not in MODEL_ROLES:
            raise ValueError(f"Unknown model_overrides role: {role}")
        normalized = normalize_model_id(value if isinstance(value, str) else None)
        if normalized:
            models[str(role)] = normalized
    return models
