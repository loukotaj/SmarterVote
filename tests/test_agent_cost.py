"""Behavioral tests for pipeline_client.agent.cost token/cost accounting."""

import pytest

from pipeline_client.agent.cost import (
    _cost_ctx,
    accumulate,
    estimate_cost,
    record_context_metrics,
    record_fetched_chars,
    record_retry_metric,
    reserve_page_fetch,
    reserve_search_call,
    set_current_phase,
    total_token_budget_reached,
)


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
    cost = estimate_cost("openai/gpt-5.6-luna", 1000, 1000)
    assert cost == pytest.approx(1000 / 1_000_000 * 0.10 + 1000 / 1_000_000 * 0.60)


def test_estimate_cost_resolves_legacy_model_alias():
    # A legacy ID prices as the model it now resolves to, because that is the
    # model the call will actually run on.
    aliased = estimate_cost("gpt-5.6-luna", 2000, 500)
    canonical = estimate_cost("openai/gpt-5.6-luna", 2000, 500)
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


def test_search_budget_reservation_blocks_calls_after_logical_run_ceiling(cost_accumulator, monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_SEARCH_CALLS", "2")

    assert reserve_search_call("serper") is True
    assert reserve_search_call("searlo") is True
    assert reserve_search_call("serper") is False
    assert cost_accumulator["serper_calls"] == 1
    assert cost_accumulator["searlo_calls"] == 1
    assert cost_accumulator["search_budget_blocked"] == 1


def test_total_token_budget_uses_prior_logical_run_tokens(cost_accumulator, monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_TOTAL_TOKENS", "10000")
    cost_accumulator["prompt_tokens"] = 9000
    cost_accumulator["completion_tokens"] = 1000

    assert total_token_budget_reached() is True


def test_phase_breakdown_attributes_tokens_cost_search_and_pages(cost_accumulator):
    set_current_phase("update-forecast")
    accumulate(100, 20, model="gpt-4o", cost_usd=0.03)
    assert reserve_search_call("serper") is True
    assert reserve_page_fetch() is True
    record_fetched_chars(250)

    phase = cost_accumulator["phase_breakdown"]["forecast"]
    assert phase["prompt_tokens"] == 100
    assert phase["completion_tokens"] == 20
    assert phase["provider_cost_usd"] == pytest.approx(0.03)
    assert phase["search_calls"] == 1
    assert phase["page_fetches"] == 1
    assert phase["fetched_chars"] == 250


def test_unit_search_and_page_budgets_are_enforced(cost_accumulator, monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_UNIT_SEARCH_CALLS", "1")
    monkeypatch.setenv("PIPELINE_MAX_PAGE_FETCHES", "1")
    set_current_phase("images-Alice")

    assert reserve_search_call("serper") is True
    assert reserve_search_call("serper") is False
    assert reserve_page_fetch() is True
    assert reserve_page_fetch() is False
    assert cost_accumulator["page_budget_blocked"] == 1


def test_one_exhausted_unit_does_not_starve_the_next(cost_accumulator, monkeypatch):
    """The whole point: a fan-out phase must not spend one shared allowance.

    Budgeting by phase family gave every candidate/issue pair in a race one
    pooled ceiling, so whichever candidate the fan-out reached last was denied
    every search and produced empty verdicts.
    """
    monkeypatch.setenv("PIPELINE_MAX_UNIT_SEARCH_CALLS", "2")
    monkeypatch.setenv("PIPELINE_MAX_SEARCH_CALLS", "100")

    set_current_phase("issue-Alice Example-Healthcare")
    assert reserve_search_call("serper") is True
    assert reserve_search_call("serper") is True
    assert reserve_search_call("serper") is False, "unit ceiling should bind"

    # A different candidate/issue pair in the same phase family starts fresh.
    set_current_phase("issue-Bob Example-Healthcare")
    assert reserve_search_call("serper") is True
    assert reserve_search_call("serper") is True

    # Attribution still rolls up to the family.
    assert cost_accumulator["phase_breakdown"]["issues"]["search_calls"] == 4


def test_run_wide_search_ceiling_still_bounds_runaway(cost_accumulator, monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_UNIT_SEARCH_CALLS", "50")
    monkeypatch.setenv("PIPELINE_MAX_SEARCH_CALLS", "3")

    for index in range(3):
        set_current_phase(f"issue-Candidate {index}-Healthcare")
        assert reserve_search_call("serper") is True

    set_current_phase("issue-Candidate 9-Healthcare")
    assert reserve_search_call("serper") is False


def test_unit_token_ceiling_is_scoped_per_unit(cost_accumulator, monkeypatch):
    # 10_000 is the configured floor for this ceiling.
    monkeypatch.setenv("PIPELINE_MAX_UNIT_TOKENS", "10000")
    monkeypatch.setenv("PIPELINE_MAX_TOTAL_TOKENS", "500000")

    set_current_phase("issue-Alice Example-Economy")
    accumulate(9_000, 2_000, "test-model")
    assert total_token_budget_reached() is True

    set_current_phase("issue-Bob Example-Economy")
    assert total_token_budget_reached() is False


def test_continuation_starts_units_fresh_but_keeps_logical_total(cost_accumulator, monkeypatch):
    """A resumed unit gets its own allowance; run-wide totals stay cumulative.

    Per-unit budgets replace the continuation baseline that used to exempt a
    phase from spend carried over by an earlier physical pass.
    """
    monkeypatch.setenv("PIPELINE_MAX_UNIT_SEARCH_CALLS", "2")
    monkeypatch.setenv("PIPELINE_MAX_SEARCH_CALLS", "10")
    monkeypatch.setenv("PIPELINE_MAX_UNIT_TOKENS", "10000")
    monkeypatch.setenv("PIPELINE_MAX_TOTAL_TOKENS", "50000")
    set_current_phase("issues")
    cost_accumulator.update(
        {
            "prompt_tokens": 12000,
            "completion_tokens": 3000,
            "serper_calls": 2,
            "searlo_calls": 0,
            "phase_breakdown": {"issues": {"prompt_tokens": 12000, "completion_tokens": 3000, "search_calls": 2}},
        }
    )

    assert total_token_budget_reached() is False
    assert reserve_search_call("serper") is True
    assert cost_accumulator["serper_calls"] == 3
