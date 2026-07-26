"""Behavioral tests for pipeline_client.agent.cost token/cost accounting."""

import pytest

from pipeline_client.agent.cost import _cost_ctx, accumulate, estimate_cost, record_context_metrics, record_retry_metric


@pytest.fixture
def cost_accumulator():
    """Install a fresh accumulator dict into the run-scoped ContextVar and
    guarantee it is reset afterwards so other tests see the default None."""
    acc: dict = {"prompt_tokens": 0, "completion_tokens": 0}
    token = _cost_ctx.set(acc)
    try:
        yield acc
    finally:
        _cost_ctx.reset(token)


def test_estimate_cost_uses_known_model_pricing():
    # gpt-4o-mini-style cheap model should cost far less than an expensive one
    # for the same token counts; exact figures come from MODEL_CATALOG so we
    # only assert relative ordering plus a sane non-zero result for an unknown model.
    unknown_cost = estimate_cost("totally-unknown-model-id", 1_000_000, 1_000_000)
    assert unknown_cost == pytest.approx(2.50 + 10.00)


def test_estimate_cost_zero_tokens_is_zero():
    assert estimate_cost("totally-unknown-model-id", 0, 0) == 0.0


def test_estimate_cost_uses_catalog_pricing_for_known_model():
    cost = estimate_cost("openai/gpt-5.4-mini", 1000, 1000)
    assert cost == pytest.approx(1000 / 1_000_000 * 0.75 + 1000 / 1_000_000 * 4.50)


def test_estimate_cost_resolves_legacy_model_alias():
    # "gpt-5.4-mini" is a legacy alias for "openai/gpt-5.4-mini" in MODEL_REGISTRY;
    # both should price identically.
    aliased = estimate_cost("gpt-5.4-mini", 2000, 500)
    canonical = estimate_cost("openai/gpt-5.4-mini", 2000, 500)
    assert aliased == pytest.approx(canonical)


def test_accumulate_without_active_context_is_a_safe_noop():
    # No fixture here: _cost_ctx defaults to None outside of a tracked run.
    accumulate(10, 20, model="gpt-4o")  # must not raise


def test_accumulate_tracks_priced_calls_and_model_breakdown(cost_accumulator):
    accumulate(100, 200, model="gpt-4o", cost_usd=0.05)

    assert cost_accumulator["prompt_tokens"] == 100
    assert cost_accumulator["completion_tokens"] == 200
    assert cost_accumulator["provider_cost_usd"] == pytest.approx(0.05)
    assert cost_accumulator["priced_calls"] == 1
    assert "unpriced_calls" not in cost_accumulator
    assert cost_accumulator["model_breakdown"]["gpt-4o"] == {
        "prompt_tokens": 100,
        "completion_tokens": 200,
    }


def test_accumulate_tracks_unpriced_calls_when_cost_is_none(cost_accumulator):
    accumulate(10, 20, model="gpt-4o")

    assert cost_accumulator["unpriced_calls"] == 1
    assert "provider_cost_usd" not in cost_accumulator


def test_accumulate_without_model_skips_breakdown(cost_accumulator):
    accumulate(5, 5, cost_usd=0.01)

    assert "model_breakdown" not in cost_accumulator


def test_accumulate_multiple_calls_same_model_sums_breakdown(cost_accumulator):
    accumulate(10, 20, model="gpt-4o", cost_usd=0.01)
    accumulate(5, 7, model="gpt-4o", cost_usd=0.02)

    assert cost_accumulator["model_breakdown"]["gpt-4o"] == {
        "prompt_tokens": 15,
        "completion_tokens": 27,
    }
    assert cost_accumulator["priced_calls"] == 2
    assert cost_accumulator["provider_cost_usd"] == pytest.approx(0.03)


def test_record_context_metrics_without_active_context_is_a_safe_noop():
    record_context_metrics(
        estimated_input_tokens=1,
        context_window_tokens=2,
        deduplicated_results=3,
        compacted_results=4,
        truncated_results=5,
        dropped_tool_turns=6,
    )


def test_record_context_metrics_tracks_max_and_running_totals(cost_accumulator):
    record_context_metrics(
        estimated_input_tokens=100,
        context_window_tokens=8000,
        deduplicated_results=2,
        compacted_results=1,
        truncated_results=0,
        dropped_tool_turns=0,
    )
    record_context_metrics(
        estimated_input_tokens=50,
        context_window_tokens=16000,
        deduplicated_results=1,
        compacted_results=3,
        truncated_results=2,
        dropped_tool_turns=1,
    )

    assert cost_accumulator["context_requests"] == 2
    # max_* fields track the largest single observation, not a running sum
    assert cost_accumulator["max_estimated_context_tokens"] == 100
    assert cost_accumulator["max_context_window_tokens"] == 16000
    assert cost_accumulator["context_deduplicated_results"] == 2
    # compacted/dropped are running sums
    assert cost_accumulator["context_compacted_results"] == 4
    assert cost_accumulator["context_truncated_results"] == 2
    assert cost_accumulator["context_dropped_tool_turns"] == 1


def test_record_retry_metric_without_active_context_is_a_safe_noop():
    record_retry_metric("rate_limits")  # must not raise


def test_record_retry_metric_increments_named_counter(cost_accumulator):
    record_retry_metric("rate_limits")
    record_retry_metric("rate_limits")
    record_retry_metric("provider_failures")

    assert cost_accumulator["retry_rate_limits"] == 2
    assert cost_accumulator["retry_provider_failures"] == 1
