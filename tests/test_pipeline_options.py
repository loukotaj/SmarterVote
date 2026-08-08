"""Behavioral tests for shared.pipeline_options.PipelineRunOptions and the
shared.pipeline_config normalization helpers it delegates to.
"""

import pytest
from pydantic import ValidationError

from shared.pipeline_config import (
    normalize_model_profile,
    normalize_pipeline_steps,
    normalize_review_providers,
    validate_model_override_keys,
)
from shared.pipeline_options import PipelineRunOptions, ResolvedPipelineRunOptions

# ---------------------------------------------------------------------------
# normalize_pipeline_steps
# ---------------------------------------------------------------------------


def test_resume_partial_defaults_false_and_is_explicitly_available():
    assert ResolvedPipelineRunOptions().resume_partial is False
    assert ResolvedPipelineRunOptions(resume_partial=True).resume_partial is True


def test_normalize_pipeline_steps_none_passthrough():
    assert normalize_pipeline_steps(None) is None


def test_normalize_pipeline_steps_dedupes_and_strips():
    assert normalize_pipeline_steps(["discovery", " discovery ", "issues"]) == ["discovery", "issues"]


def test_normalize_pipeline_steps_empty_list_raises():
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_pipeline_steps([])


def test_normalize_pipeline_steps_unknown_step_raises():
    with pytest.raises(ValueError, match="Unknown enabled_steps: not-a-step"):
        normalize_pipeline_steps(["discovery", "not-a-step"])


def test_normalize_pipeline_steps_filters_non_string_entries():
    assert normalize_pipeline_steps(["discovery", 123, None]) == ["discovery"]


# ---------------------------------------------------------------------------
# normalize_review_providers
# ---------------------------------------------------------------------------


def test_normalize_review_providers_none_passthrough():
    assert normalize_review_providers(None) is None


def test_normalize_review_providers_lowercases_and_dedupes():
    assert normalize_review_providers(["Claude", "claude", "GEMINI"]) == ["claude", "gemini"]


def test_normalize_review_providers_empty_list_raises():
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_review_providers([])


def test_normalize_review_providers_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown review_providers: chatgpt"):
        normalize_review_providers(["claude", "chatgpt"])


# ---------------------------------------------------------------------------
# normalize_model_profile
# ---------------------------------------------------------------------------


def test_normalize_model_profile_none_passthrough():
    assert normalize_model_profile(None) is None


def test_normalize_model_profile_lowercases_valid_value():
    assert normalize_model_profile("Premium") == "premium"


def test_normalize_model_profile_maps_retired_names_forward():
    """Queue items outlive profile renames, so an old name must still validate."""
    assert normalize_model_profile("economy") == "default"
    assert normalize_model_profile("balanced") == "default"
    assert normalize_model_profile("QUALITY") == "premium"


def test_normalize_model_profile_invalid_raises():
    with pytest.raises(ValueError, match="model_profile must be one of"):
        normalize_model_profile("ultra-premium")


# ---------------------------------------------------------------------------
# validate_model_override_keys
# ---------------------------------------------------------------------------


def test_validate_model_override_keys_none_passthrough():
    assert validate_model_override_keys(None) is None


def test_validate_model_override_keys_accepts_known_roles():
    result = validate_model_override_keys({"primary": "openai/gpt-5.4-mini"})
    assert result == {"primary": "openai/gpt-5.4-mini"}


def test_validate_model_override_keys_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unknown model_overrides roles: not_a_role"):
        validate_model_override_keys({"not_a_role": "some-model"})


# ---------------------------------------------------------------------------
# PipelineRunOptions (exercises the field validators end-to-end)
# ---------------------------------------------------------------------------


def test_pipeline_run_options_defaults_are_all_none():
    options = PipelineRunOptions()
    assert options.cheap_mode is None
    assert options.enabled_steps is None
    assert options.model_overrides is None


def test_pipeline_run_options_validates_max_candidates_minimum():
    with pytest.raises(ValidationError, match="max_candidates must be at least 1"):
        PipelineRunOptions(max_candidates=0)


def test_pipeline_run_options_accepts_positive_max_candidates():
    assert PipelineRunOptions(max_candidates=5).max_candidates == 5


def test_pipeline_run_options_normalizes_candidate_names():
    options = PipelineRunOptions(candidate_names=[" Jane Doe ", "Jane Doe", "John Smith", "", "   "])
    assert options.candidate_names == ["Jane Doe", "John Smith"]


def test_pipeline_run_options_candidate_names_all_blank_becomes_none():
    options = PipelineRunOptions(candidate_names=["", "   "])
    assert options.candidate_names is None


def test_pipeline_run_options_rejects_iteration_without_review():
    with pytest.raises(ValidationError, match="'iteration' requires 'review'"):
        PipelineRunOptions(enabled_steps=["discovery", "iteration"])


def test_pipeline_run_options_accepts_iteration_with_review():
    options = PipelineRunOptions(enabled_steps=["review", "iteration"])
    assert options.enabled_steps == ["review", "iteration"]


def test_pipeline_run_options_rejects_unknown_enabled_step():
    with pytest.raises(ValidationError, match="Unknown enabled_steps"):
        PipelineRunOptions(enabled_steps=["not-a-real-step"])


def test_pipeline_run_options_rejects_unknown_model_override_role():
    with pytest.raises(ValidationError, match="Unknown model_overrides roles"):
        PipelineRunOptions(model_overrides={"not_a_role": "some-model"})


def test_pipeline_run_options_rejects_unknown_model_profile():
    with pytest.raises(ValidationError, match="model_profile must be one of"):
        PipelineRunOptions(model_profile="ultra-premium")


def test_pipeline_run_options_rejects_empty_review_providers_list():
    with pytest.raises(ValidationError, match="cannot be empty"):
        PipelineRunOptions(review_providers=[])


def test_resolved_pipeline_run_options_applies_execution_defaults():
    resolved = ResolvedPipelineRunOptions()
    assert resolved.cheap_mode is True
    assert resolved.save_artifact is True
    assert resolved.force_fresh is False
    assert resolved.baseline_source == "latest"
    assert resolved.target_no_info is False


def test_resolved_pipeline_run_options_allows_overriding_defaults():
    resolved = ResolvedPipelineRunOptions(cheap_mode=False, baseline_source="published")
    assert resolved.cheap_mode is False
    assert resolved.baseline_source == "published"
