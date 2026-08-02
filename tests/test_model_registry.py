"""Tests for model-profile resolution, incl. the dedicated roster role."""

from pipeline_client.agent.model_registry import (
    CHEAP_GEMINI_MODEL,
    CHEAP_MODEL,
    DEEPSEEK_FLASH_MODEL,
    DEEPSEEK_PRO_MODEL,
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROK_MODEL,
    MID_MODEL,
    ROSTER_MODEL,
    resolve_run_models,
)


def test_economy_roster_role_upgrades_beyond_primary():
    """Roster sync/verify must use a stronger model than the economy primary.

    Regression: economy primary (DeepSeek Flash) kept retired ex-incumbents /
    prior-cycle candidates on some house rosters, so the roster steps run on a
    stronger instruction-follower even in cheap mode.
    """
    models = resolve_run_models(cheap_mode=True)
    assert models["primary"] == DEEPSEEK_FLASH_MODEL
    assert models["roster"] == ROSTER_MODEL
    assert models["roster"] != models["primary"]


def test_every_profile_defines_a_roster_role():
    for cheap_mode in (True, False, None):
        models = resolve_run_models(cheap_mode=cheap_mode)
        assert models.get("roster"), f"missing roster role for cheap_mode={cheap_mode}"


def test_balanced_profile_pairs_a_flash_primary_with_a_cheap_sub_agent():
    models = resolve_run_models()
    assert models["primary"] == CHEAP_GEMINI_MODEL
    assert models["small"] == CHEAP_MODEL


def test_quality_profile_upgrades_research_and_every_reviewer():
    """Quality moves research to the mid tier and reviewers to their flagships.

    Sub-agent work stays on the cheap tier: it is called once per candidate/issue
    pair, and the quality decision is made by review, not by the sub-agent.
    """
    models = resolve_run_models(cheap_mode=False)
    assert models["primary"] == MID_MODEL
    assert models["roster"] == MID_MODEL
    assert models["small"] == CHEAP_MODEL
    assert models["review_claude"] == DEFAULT_CLAUDE_MODEL
    assert models["review_gemini"] == DEFAULT_GEMINI_MODEL
    assert models["review_grok"] == DEFAULT_GROK_MODEL


def test_every_profile_role_resolves_to_a_catalogued_model():
    """A role pointing at a model with no catalog entry silently loses costing."""
    from pipeline_client.agent.model_registry import MODEL_CATALOG, PROFILE_DEFAULTS

    for profile, roles in PROFILE_DEFAULTS.items():
        for role, model in roles.items():
            assert model in MODEL_CATALOG, f"{profile}.{role} -> {model} is not in MODEL_CATALOG"
