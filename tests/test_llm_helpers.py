"""Behavioral tests for the pure helper functions in pipeline_client.agent.llm:
_provider_usage_cost, _accumulate_usage, _get_openrouter_client,
_openrouter_request_timeout_seconds, _env_int, _normalize_source,
_normalize_candidate, and _ensure_dict.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import pipeline_client.agent.llm as llm_module
from pipeline_client.agent.llm import (
    _accumulate_usage,
    _await_with_run_budget,
    _ensure_dict,
    _env_int,
    _get_openrouter_client,
    _normalize_candidate,
    _normalize_source,
    _openrouter_request_timeout_seconds,
    _provider_usage_cost,
)

# ---------------------------------------------------------------------------
# _provider_usage_cost / _accumulate_usage
# ---------------------------------------------------------------------------


def test_provider_usage_cost_none_usage_returns_none():
    assert _provider_usage_cost(None) is None


def test_provider_usage_cost_reads_direct_cost_attribute():
    usage = MagicMock(spec=["cost"])
    usage.cost = 0.5
    assert _provider_usage_cost(usage) == 0.5


def test_provider_usage_cost_missing_extra_dict_returns_none():
    usage = MagicMock(spec=["cost", "model_extra"])
    usage.cost = None
    usage.model_extra = "not-a-dict"
    assert _provider_usage_cost(usage) is None


def test_provider_usage_cost_extra_dict_without_cost_key_returns_none():
    usage = MagicMock(spec=["cost", "model_extra"])
    usage.cost = None
    usage.model_extra = {"other": 1}
    assert _provider_usage_cost(usage) is None


def test_accumulate_usage_skips_when_response_has_no_usage():
    resp = MagicMock(spec=[])  # no `usage` attribute at all -> getattr returns None

    with patch("pipeline_client.agent.llm.accumulate") as mock_accumulate:
        _accumulate_usage(resp, "gpt-4o")

    mock_accumulate.assert_not_called()


def test_accumulate_usage_defaults_none_token_counts_to_zero():
    resp = MagicMock()
    resp.usage.prompt_tokens = None
    resp.usage.completion_tokens = None
    resp.usage.cost = 0.1

    with patch("pipeline_client.agent.llm.accumulate") as mock_accumulate:
        _accumulate_usage(resp, "gpt-4o")

    mock_accumulate.assert_called_once_with(0, 0, "gpt-4o", cost_usd=pytest.approx(0.1))


# ---------------------------------------------------------------------------
# _get_openrouter_client
# ---------------------------------------------------------------------------


def test_get_openrouter_client_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(llm_module, "_openrouter_client", None)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is not set"):
        _get_openrouter_client()


def test_get_openrouter_client_creates_and_reuses_client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-1")
    monkeypatch.setattr(llm_module, "_openrouter_client", None)

    first = _get_openrouter_client()
    second = _get_openrouter_client()

    assert first is second
    assert first.api_key == "test-key-1"

    monkeypatch.setattr(llm_module, "_openrouter_client", None)


def test_get_openrouter_client_recreates_when_api_key_changes(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-1")
    monkeypatch.setattr(llm_module, "_openrouter_client", None)
    first = _get_openrouter_client()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-2")
    second = _get_openrouter_client()

    assert second is not first
    assert second.api_key == "test-key-2"

    monkeypatch.setattr(llm_module, "_openrouter_client", None)


# ---------------------------------------------------------------------------
# _openrouter_request_timeout_seconds
# ---------------------------------------------------------------------------


def test_openrouter_request_timeout_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("OPENROUTER_REQUEST_TIMEOUT_SECONDS", raising=False)
    assert _openrouter_request_timeout_seconds() == 240.0


def test_openrouter_request_timeout_parses_valid_value(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REQUEST_TIMEOUT_SECONDS", "120")
    assert _openrouter_request_timeout_seconds() == 120.0


def test_openrouter_request_timeout_clamps_to_minimum(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REQUEST_TIMEOUT_SECONDS", "5")
    assert _openrouter_request_timeout_seconds() == 30.0


def test_openrouter_request_timeout_invalid_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REQUEST_TIMEOUT_SECONDS", "not-a-number")
    assert _openrouter_request_timeout_seconds() == 240.0


# ---------------------------------------------------------------------------
# _env_int
# ---------------------------------------------------------------------------


def test_env_int_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_TEST_ENV_INT", raising=False)
    assert _env_int("SOME_TEST_ENV_INT", 7) == 7


def test_env_int_parses_valid_value(monkeypatch):
    monkeypatch.setenv("SOME_TEST_ENV_INT", "42")
    assert _env_int("SOME_TEST_ENV_INT", 7) == 42


def test_env_int_enforces_minimum(monkeypatch):
    monkeypatch.setenv("SOME_TEST_ENV_INT", "-5")
    assert _env_int("SOME_TEST_ENV_INT", 7, minimum=0) == 0


def test_env_int_invalid_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SOME_TEST_ENV_INT", "not-an-int")
    assert _env_int("SOME_TEST_ENV_INT", 7) == 7


# ---------------------------------------------------------------------------
# _await_with_run_budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_await_with_run_budget_without_budget_uses_requested_timeout():
    async def quick():
        return "done"

    result = await _await_with_run_budget(
        quick(), run_budget=None, requested_timeout=5.0, operation="test op", timeout_result=None
    )

    assert result == "done"


@pytest.mark.asyncio
async def test_await_with_run_budget_uses_bounded_timeout_from_budget():
    async def quick():
        return "done"

    fake_budget = MagicMock()
    fake_budget.bounded_timeout.return_value = 1.0

    result = await _await_with_run_budget(
        quick(), run_budget=fake_budget, requested_timeout=5.0, operation="test op", timeout_result=None
    )

    assert result == "done"
    fake_budget.bounded_timeout.assert_called_once_with(5.0, minimum_seconds=2.0, operation="test op")


@pytest.mark.asyncio
async def test_await_with_run_budget_returns_timeout_result_on_timeout():
    """An isolated tool timeout resolves to timeout_result instead of propagating.

    This is the point of the timeout_result argument: a single slow tool call
    surfaces to the model as a usable failure value and the agent loop keeps
    going, rather than raising and ending the run.
    """

    async def slow():
        await asyncio.sleep(1.0)
        return "never"

    sentinel = {"found": False, "error": "Election lookup timed out."}

    result = await _await_with_run_budget(
        slow(), run_budget=None, requested_timeout=0.01, operation="test op", timeout_result=sentinel
    )

    assert result is sentinel


# ---------------------------------------------------------------------------
# _normalize_source / _normalize_candidate
# ---------------------------------------------------------------------------


def test_normalize_source_ignores_non_dict_input():
    # Must not raise for None or non-dict source values.
    _normalize_source(None, "2026-01-01T00:00:00Z")
    _normalize_source("not-a-dict", "2026-01-01T00:00:00Z")


def test_normalize_source_sets_defaults_and_normalizes_type():
    source = {"url": "https://example.gov/bio", "type": "official site"}

    _normalize_source(source, "2026-01-01T00:00:00Z")

    assert source["last_accessed"] == "2026-01-01T00:00:00Z"
    assert source["type"] == "government"


def test_normalize_source_preserves_existing_last_accessed():
    source = {"url": "https://x.com", "type": "website", "last_accessed": "2020-01-01T00:00:00Z"}

    _normalize_source(source, "2026-01-01T00:00:00Z")

    assert source["last_accessed"] == "2020-01-01T00:00:00Z"


def test_normalize_candidate_sets_all_defaults():
    candidate: dict = {}

    _normalize_candidate(candidate, "2026-01-01T00:00:00Z")

    assert candidate["image_url"] is None
    assert candidate["career_history"] == []
    assert candidate["education"] == []
    assert candidate["donor_summary"] is None
    assert candidate["donor_sources"] == []
    assert candidate["voting_sources"] == []
    assert candidate["links"] == []


def test_normalize_candidate_converts_empty_string_image_url_to_none():
    candidate = {"image_url": ""}

    _normalize_candidate(candidate, "2026-01-01T00:00:00Z")

    assert candidate["image_url"] is None


def test_normalize_candidate_normalizes_nested_sources():
    candidate = {
        "summary_sources": [{"url": "https://a.com", "type": "ballotpedia"}],
        "issues": {
            "Healthcare": {"sources": [{"url": "https://b.gov", "type": "official"}]},
            "Economy": "not-a-dict",  # must be tolerated, not normalized
        },
        "career_history": [
            {"source": {"url": "https://c.com", "type": "wiki"}},
            "not-a-dict-entry",
        ],
        "education": [
            {"source": {"url": "https://d.com", "type": "social"}},
        ],
        "donor_sources": [{"url": "https://e.com", "type": "campaign"}],
        "voting_sources": [{"url": "https://f.gov", "type": "govtrack"}],
    }

    _normalize_candidate(candidate, "2026-01-01T00:00:00Z")

    assert candidate["summary_sources"][0]["type"] == "website"
    assert candidate["issues"]["Healthcare"]["sources"][0]["type"] == "government"
    assert candidate["career_history"][0]["source"]["type"] == "website"
    assert candidate["education"][0]["source"]["type"] == "social_media"
    assert candidate["donor_sources"][0]["type"] == "website"
    assert candidate["voting_sources"][0]["type"] == "government"
    for entry in candidate["summary_sources"] + candidate["donor_sources"] + candidate["voting_sources"]:
        assert entry["last_accessed"] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# _ensure_dict
# ---------------------------------------------------------------------------


def test_ensure_dict_passthrough_for_dict():
    log = MagicMock()
    assert _ensure_dict({"a": 1}, "phase", log) == {"a": 1}
    log.assert_not_called()


def test_ensure_dict_unwraps_single_item_list():
    log = MagicMock()
    result = _ensure_dict([{"a": 1}], "phase", log)
    assert result == {"a": 1}
    log.assert_called_once()
    assert "unwrapping single dict" in log.call_args.args[1]


def test_ensure_dict_merges_multiple_dicts_in_list():
    log = MagicMock()
    result = _ensure_dict([{"a": 1}, {"b": 2}], "phase", log)
    assert result == {"a": 1, "b": 2}
    assert "merging" in log.call_args.args[1]


def test_ensure_dict_raises_for_list_with_no_dicts():
    log = MagicMock()
    with pytest.raises(ValueError, match="expected dict"):
        _ensure_dict(["not", "a", "dict"], "phase", log)


def test_ensure_dict_raises_for_non_dict_non_list():
    log = MagicMock()
    with pytest.raises(ValueError, match="expected dict, got str"):
        _ensure_dict("plain string", "phase", log)
