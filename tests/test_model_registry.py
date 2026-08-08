"""Tests for the model catalog and profile resolution.

These lock down the invariants that a wrong model choice would silently break.
Prices and context windows are *not* tested here — they are provider facts,
verified against the live API by ``scripts/check_model_catalog.py``, which the
mocked test suite cannot reach.
"""

import pytest

from pipeline_client.agent.model_registry import (
    ADJUDICATOR_MODEL,
    DEFAULT_CHAMBER_FORECAST_MODEL,
    DEFAULT_RESEARCH_MODEL,
    MODEL_CATALOG,
    MODEL_ESCALATION,
    MODEL_PROFILES,
    MODEL_ROLES,
    PREMIUM_RESEARCH_MODEL,
    PROFILE_DEFAULTS,
    SMALL_MODEL,
    escalation_for,
    intelligence_of,
    resolve_run_models,
)
from shared.model_catalog import label_for, normalize_model_id, normalize_profile_name


def test_default_profile_is_what_cheap_mode_selects():
    models = resolve_run_models(cheap_mode=True)
    assert models["profile"] == "default"
    assert models["primary"] == DEFAULT_RESEARCH_MODEL
    assert models["small"] == SMALL_MODEL


def test_premium_profile_upgrades_research_roster_and_every_reviewer():
    """Premium buys a stronger researcher and three flagship reviewers.

    Sub-agent work deliberately stays on the small tier: it runs once per
    candidate/issue pair, and quality is decided by review, not by sub-agents.
    """
    default = resolve_run_models(cheap_mode=True)
    premium = resolve_run_models(cheap_mode=False)
    assert premium["profile"] == "premium"
    assert premium["primary"] == PREMIUM_RESEARCH_MODEL
    assert premium["roster"] == PREMIUM_RESEARCH_MODEL
    assert premium["small"] == SMALL_MODEL
    for role in ("review_claude", "review_gemini", "review_grok"):
        assert premium[role] != default[role], f"{role} should differ between profiles"


def test_unset_cheap_mode_resolves_to_the_cheap_profile():
    """An unset cheap_mode used to select a middle profile that was worse *and*
    dearer than the cheap one. There is no middle profile now, and silently
    spending more than the caller asked for is the wrong default either way."""
    assert resolve_run_models(cheap_mode=None)["profile"] == "default"
    assert resolve_run_models({})["profile"] == "default"


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [("economy", "default"), ("balanced", "default"), ("quality", "premium")],
)
def test_retired_profile_names_still_resolve(legacy, expected):
    """Queued items and stored run records outlive a profile rename."""
    assert normalize_profile_name(legacy) == expected
    assert resolve_run_models({"model_profile": legacy})["profile"] == expected


def test_unknown_profile_name_is_rejected():
    with pytest.raises(ValueError):
        normalize_profile_name("cheapest-possible")


def test_every_profile_defines_every_role():
    for profile in ("default", "premium"):
        for role in MODEL_ROLES:
            assert PROFILE_DEFAULTS[profile].get(role), f"missing {role} for {profile}"


def test_every_profile_role_resolves_to_a_catalogued_model():
    """A role pointing at an uncatalogued model silently loses cost tracking."""
    for profile, roles in PROFILE_DEFAULTS.items():
        for role, model in roles.items():
            assert model in MODEL_CATALOG, f"{profile}.{role} -> {model} is not in MODEL_CATALOG"


def test_roster_is_never_less_capable_than_research():
    """Roster verification decides who appears on a ballot.

    It may share the research model, but it must never be the *weaker* of the
    two. It once ran on a model scoring 36.5 against research's 49.9 — chosen
    when the ordering was the other way round and never revisited.
    """
    for profile, roles in PROFILE_DEFAULTS.items():
        roster_iq = intelligence_of(roles["roster"])
        primary_iq = intelligence_of(roles["primary"])
        assert roster_iq >= primary_iq, f"{profile}: roster {roster_iq} is weaker than primary {primary_iq}"


def test_every_escalation_climbs_the_intelligence_index():
    """An escalation that does not buy capability is worse than no escalation:
    it costs more and returns a weaker answer. The map once sent the default
    research model to one scoring 12 points lower at 6.7x the input price."""
    assert MODEL_ESCALATION, "escalation map should not be empty"
    for source, target in MODEL_ESCALATION.items():
        source_iq = intelligence_of(source)
        target_iq = intelligence_of(target)
        assert source_iq is not None and target_iq is not None
        assert target_iq > source_iq, f"{source} ({source_iq}) -> {target} ({target_iq}) is not an upgrade"


def test_escalation_is_defined_for_every_profile_primary():
    """A stalled research loop with nowhere to climb just fails."""
    for profile, roles in PROFILE_DEFAULTS.items():
        assert escalation_for(roles["primary"]), f"{profile}.primary has no escalation target"


def test_escalation_normalizes_legacy_model_ids():
    assert escalation_for("deepseek-v4-flash-0731") == escalation_for(DEFAULT_RESEARCH_MODEL)


def test_adjudicator_never_judges_evidence_it_produced():
    """The roster gate's only claim to independence is that the model judging
    the evidence is not the model that produced it. Roster edits are made from
    both roster-phase loops and metadata/refinement loops, so the adjudicator
    must differ from `roster` *and* `primary`, in every profile."""
    assert ADJUDICATOR_MODEL in MODEL_CATALOG
    for profile, roles in PROFILE_DEFAULTS.items():
        assert ADJUDICATOR_MODEL != roles["primary"], f"{profile}: adjudicator == primary"
        assert ADJUDICATOR_MODEL != roles["roster"], f"{profile}: adjudicator == roster"


def test_model_overrides_win_over_profile_defaults():
    models = resolve_run_models({"model_overrides": {"roster": SMALL_MODEL}}, cheap_mode=True)
    assert models["roster"] == SMALL_MODEL
    assert models["primary"] == DEFAULT_RESEARCH_MODEL


def test_unknown_override_role_is_rejected():
    with pytest.raises(ValueError):
        resolve_run_models({"model_overrides": {"reviewer": SMALL_MODEL}})


def test_legacy_keyword_overrides_beat_model_overrides():
    models = resolve_run_models(
        {"model_overrides": {"primary": SMALL_MODEL}},
        research_model=PREMIUM_RESEARCH_MODEL,
    )
    assert models["primary"] == PREMIUM_RESEARCH_MODEL


def test_every_legacy_alias_points_at_a_live_catalog_entry():
    """An alias resolving to nothing costs a run its price data."""
    from shared.model_catalog import LEGACY_MODEL_ALIASES

    for alias, target in LEGACY_MODEL_ALIASES.items():
        assert target in MODEL_CATALOG, f"alias {alias} -> {target} is not catalogued"


def test_chamber_forecast_model_is_catalogued():
    assert DEFAULT_CHAMBER_FORECAST_MODEL in MODEL_CATALOG


def test_retired_models_render_as_themselves_not_their_replacement():
    """A run that used gpt-5.4 must not display as the model that replaced it."""
    assert label_for("openai/gpt-5.4") == "GPT-5.4"
    assert normalize_model_id("openai/gpt-5.4") == PREMIUM_RESEARCH_MODEL
    assert label_for(DEFAULT_RESEARCH_MODEL) == MODEL_CATALOG[DEFAULT_RESEARCH_MODEL].label
    assert label_for("something-we-never-ran") == "something-we-never-ran"


def test_profiles_are_exactly_default_premium_and_custom():
    assert MODEL_PROFILES == {"default", "premium", "custom"}
