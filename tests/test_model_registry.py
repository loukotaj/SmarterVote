"""Tests for model-profile resolution, incl. the dedicated roster role."""

from pipeline_client.agent.model_registry import DEEPSEEK_FLASH_MODEL, DEEPSEEK_PRO_MODEL, ROSTER_MODEL, resolve_run_models


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


def test_balanced_profile_uses_deepseek_flash_for_small_tasks():
    models = resolve_run_models()
    assert models["primary"] == "google/gemini-2.5-flash"
    assert models["small"] == DEEPSEEK_FLASH_MODEL


def test_quality_profile_uses_deepseek_pro_for_research_roles():
    models = resolve_run_models(cheap_mode=False)
    assert models["primary"] == DEEPSEEK_PRO_MODEL
    assert models["small"] == DEEPSEEK_PRO_MODEL
    assert models["roster"] == DEEPSEEK_PRO_MODEL
