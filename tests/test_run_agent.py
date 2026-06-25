"""Tests for run_agent orchestration and _load_existing helper."""

import asyncio
import json
import os
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pipeline_client.agent.agent import _load_existing, _normalize_schema_fields, _sanitize_polling, run_agent
from pipeline_client.agent.phases import _reconcile_candidates_with_authoritative_roster, _run_iteration_pass, _sanitize_roster
from pipeline_client.agent.prompts import CANONICAL_ISSUES
from pipeline_client.backend.handlers.agent import HandoffTriggered


@pytest.fixture(autouse=True)
def no_openrouter_key(monkeypatch):
    """Unit tests mock agent phases; never call real OpenRouter reviews."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Load existing data tests
# ---------------------------------------------------------------------------


def test_load_existing_returns_none_for_missing():
    """_load_existing returns None when no published file exists."""
    result = _load_existing("nonexistent-race-9999")
    assert result is None


def test_load_existing_reads_file(tmp_path):
    """_load_existing reads and parses a published JSON file."""
    test_data = {"id": "test-race", "candidates": []}
    published_dir = tmp_path / "data" / "published"
    published_dir.mkdir(parents=True)
    test_file = published_dir / "__test_tmp_load_existing__.json"

    with test_file.open("w") as f:
        json.dump(test_data, f)

    # Redirect _load_existing's base path to tmp_path so no real data/ files are created
    fake_file = tmp_path / "pipeline_client" / "agent" / "agent.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.touch()
    with patch("pipeline_client.agent.agent.__file__", str(fake_file)):
        result = _load_existing("__test_tmp_load_existing__")
    assert result is not None
    assert result["id"] == "test-race"


def test_normalize_schema_fields_coerces_candidate_link_strings():
    """Raw link strings from model output should be saved as CandidateLink objects."""
    race_json = {
        "id": "test-race",
        "title": "Test Race",
        "office": "Governor",
        "jurisdiction": "Test",
        "state": "TS",
        "election_date": "2026-11-03",
        "candidates": [
            {
                "name": "Alice",
                "links": [
                    "https://example.com/alice",
                    {"url": "https://example.com/alice", "title": "Duplicate"},
                    {"url": "https://example.com/news", "title": "News", "type": "bad-type"},
                ],
            }
        ],
    }

    _normalize_schema_fields(race_json, lambda *_: None)

    assert race_json["candidates"][0]["links"] == [
        {"url": "https://example.com/alice", "title": "https://example.com/alice", "type": "other"},
        {"url": "https://example.com/news", "title": "News", "type": "other"},
    ]


# ---------------------------------------------------------------------------
# Full agent tests (multi-phase)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_fresh():
    """run_agent with no existing data runs discovery \u2192 issues \u2192 refine."""
    discovery_result = {
        "id": "test-2024",
        "candidates": [{"name": "Alice", "issues": {}}],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = {}
        mock_loop.side_effect = [discovery_result] + [{"image_url": None}] + [{}] * 15

        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["id"] == "test-2024"
    assert "updated_utc" in result
    assert result["generator"] == ["deepseek/deepseek-v4-flash", "openai/gpt-5-nano"]
    # discovery + image + 12 issue sub-agents + finance + refine + meta refine = 17
    assert mock_loop.call_count == 17


@pytest.mark.asyncio
async def test_run_agent_fresh_no_candidates():
    """run_agent returns early when discovery finds no candidates."""
    discovery_result = {
        "id": "empty-2024",
        "candidates": [],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "empty-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["id"] == "empty-2024"
    assert result["candidates"] == []
    # Only 1 call (discovery), no issue research or refinement
    assert mock_loop.call_count == 1


@pytest.mark.asyncio
async def test_run_agent_rejects_empty_discovery_before_review():
    """An empty profile should fail before review models spend more tokens."""
    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock) as mock_reviews,
    ):
        mock_loop.return_value = {"id": "empty-reviewed-2026", "candidates": []}

        with pytest.raises(ValueError, match="Stopping before review"):
            await run_agent("empty-reviewed-2026", cheap_mode=True, reject_empty_candidates=True)

    mock_reviews.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_agent_includes_prior_continuation_metrics():
    discovery_result = {"id": "continued-2026", "candidates": [{"name": "Alice", "issues": {}}]}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "continued-2026",
            cheap_mode=True,
            enabled_steps=["discovery"],
            prior_agent_metrics={
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "provider_cost_usd": 0.00123,
                "priced_calls": 2,
                "unpriced_calls": 0,
                "model_breakdown": {"openai/gpt-5.4-mini": {"prompt_tokens": 100, "completion_tokens": 20}},
            },
        )

    assert result["agent_metrics"]["total_tokens"] == 120
    assert result["agent_metrics"]["cost_usd"] == pytest.approx(0.00123)
    assert result["agent_metrics"]["cost_source"] == "provider"


@pytest.mark.asyncio
async def test_run_agent_removes_term_limited_incumbent_from_fresh_roster():
    """Discovery may mention a term-limited officeholder, but issues should only run for candidates."""
    discovery_result = {
        "id": "ga-governor-2026",
        "candidates": [
            {
                "name": "Brian Kemp",
                "party": "Republican Party",
                "incumbent": True,
                "summary": "Brian Kemp is term-limited from running again in 2026.",
                "issues": {},
            },
            {
                "name": "Chris Carr",
                "party": "Republican Party",
                "incumbent": False,
                "summary": "Chris Carr is running for governor.",
                "issues": {},
            },
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "ga-governor-2026",
            cheap_mode=True,
            enabled_steps=["discovery"],
        )

    assert [candidate["name"] for candidate in result["candidates"]] == ["Chris Carr"]
    assert mock_loop.call_count == 1


@pytest.mark.asyncio
async def test_run_agent_preserves_oversized_fresh_roster():
    """Oversized primary-style rosters remain authoritative in the draft."""
    discovery_result = {
        "id": "ga-governor-2026",
        "candidates": [
            {
                "name": f"Candidate {idx}",
                "party": "Democratic" if idx < 6 else "Republican",
                "incumbent": False,
                "issues": {},
            }
            for idx in range(1, 11)
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "ga-governor-2026",
            cheap_mode=True,
            enabled_steps=["discovery"],
        )

    assert [candidate["name"] for candidate in result["candidates"]] == [f"Candidate {idx}" for idx in range(1, 11)]
    assert "candidate_limit_note" not in result


@pytest.mark.asyncio
async def test_run_agent_propagates_control_exceptions_from_step_tracker():
    """Handoff/cancel signals from tracker callbacks must stop the current invocation."""
    discovery_result = {
        "id": "ga-governor-2026",
        "candidates": [{"name": "Alice", "issues": {}}],
    }

    def _raise_handoff(_step, **_kwargs):
        raise HandoffTriggered("continuation-item", ["issues"], "continuation-run")

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        with pytest.raises(HandoffTriggered):
            await run_agent(
                "ga-governor-2026",
                cheap_mode=True,
                enabled_steps=["discovery"],
                step_tracker={"start": _raise_handoff},
            )


@pytest.mark.asyncio
async def test_run_agent_propagates_control_exceptions_from_issue_progress():
    """Deep issue progress callbacks must not swallow handoff/cancel signals."""
    discovery_result = {
        "id": "ga-governor-2026",
        "candidates": [{"name": "Alice", "issues": {}}],
    }

    def _raise_handoff(step, **_kwargs):
        if step == "issues":
            raise HandoffTriggered("continuation-item", ["issues"], "continuation-run")

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = {}
        mock_loop.side_effect = [discovery_result] + [{}] * 12
        with pytest.raises(HandoffTriggered):
            await run_agent(
                "ga-governor-2026",
                cheap_mode=True,
                enabled_steps=["discovery", "issues"],
                step_tracker={"progress": _raise_handoff},
            )


@pytest.mark.asyncio
async def test_run_agent_update_mode():
    """run_agent with existing data but no candidates falls back to fresh run."""
    existing = {"id": "test-2024", "candidates": [], "updated_utc": "2024-01-01"}
    updated = {"id": "test-2024", "candidates": [{"name": "Bob", "issues": {}}]}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        mock_loop.return_value = {}
        mock_loop.side_effect = [updated, {"image_url": None}] + [{}] * 15
        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["id"] == "test-2024"
    # Falls back to fresh: discovery + image + issue research + finance + refinement.
    assert mock_loop.call_count >= 16


@pytest.mark.asyncio
async def test_discovery_only_update_uses_update_discovery_phases():
    existing = {
        "id": "al-senate-2026",
        "description": "Keep this researched description.",
        "polling": [{"pollster": "Existing Poll"}],
        "candidates": [{"name": "Alice", "party": "Democratic", "issues": {}}],
        "updated_utc": "2026-01-01T00:00:00Z",
    }

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = {}
        result = await run_agent(
            "al-senate-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
        )

    assert [call.kwargs["phase_name"] for call in mock_loop.call_args_list] == [
        "roster-sync",
        "roster-verify",
        "update-meta",
    ]


@pytest.mark.asyncio
async def test_run_agent_force_fresh_with_empty_dict():
    """run_agent with existing_data={} forces fresh run."""
    discovery_result = {
        "id": "test-2024",
        "candidates": [],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("test-2024", cheap_mode=True, existing_data={})

    # Empty dict is falsy, so it should run fresh (not update)
    assert result["id"] == "test-2024"


@pytest.mark.asyncio
async def test_run_agent_normalizes_output():
    """run_agent sets defaults even when agent returns minimal JSON."""
    minimal = {"candidates": []}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = minimal
        result = await run_agent(
            "race-2024",
            cheap_mode=True,
            existing_data={},
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["id"] == "race-2024"
    assert "updated_utc" in result
    assert result["generator"] == ["deepseek/deepseek-v4-flash", "openai/gpt-5-nano"]


@pytest.mark.asyncio
async def test_run_agent_adds_source_timestamps():
    """run_agent adds last_accessed to sources that lack it."""
    discovery_result = {
        "id": "ts-2024",
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Healthcare": {
                        "stance": "Supports ACA.",
                        "confidence": "high",
                        "sources": [{"url": "https://example.com", "type": "news", "title": "Article"}],
                    }
                },
            }
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("ts-2024", cheap_mode=True, existing_data={})

    source = result["candidates"][0]["issues"]["Healthcare"]["sources"][0]
    assert "last_accessed" in source


@pytest.mark.asyncio
async def test_run_agent_normalizes_summary_sources():
    discovery_result = {
        "id": "summary-sources-2024",
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [{"url": "https://ballotpedia.org/Alice", "type": "ballotpedia"}],
                "issues": {},
            }
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("summary-sources-2024", cheap_mode=True, existing_data={})

    source = result["candidates"][0]["summary_sources"][0]
    assert source["type"] == "website"
    assert source["last_accessed"]


@pytest.mark.asyncio
async def test_run_agent_adds_donor_source_timestamps():
    """run_agent normalizes candidate shape including donor_summary."""
    discovery_result = {
        "id": "donors-2024",
        "candidates": [
            {
                "name": "Alice",
                "issues": {},
                "donor_summary": "Alice received most funding from tech industry PACs.",
                "donor_source_url": "https://example.com/donors",
                "donor_sources": [
                    {
                        "url": "https://example.com/donors",
                        "type": "finance",
                        "title": "Donor data",
                    }
                ],
            }
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("donors-2024", cheap_mode=True, existing_data={})

    candidate = result["candidates"][0]
    assert candidate["donor_summary"] == "Alice received most funding from tech industry PACs."
    assert candidate["donor_source_url"] == "https://example.com/donors"
    assert candidate["donor_sources"][0]["last_accessed"]


@pytest.mark.asyncio
async def test_run_agent_model_selection():
    """run_agent selects the configured primary model for cheap, quality, and balanced profiles."""
    discovery_result = {"id": "m-2024", "candidates": []}

    cases = [
        (True, "deepseek/deepseek-v4-flash"),
        (False, "google/gemini-2.5-flash"),
        (None, "google/gemini-2.5-flash"),
    ]

    for cheap_mode, expected_model in cases:
        with (
            patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
            patch("pipeline_client.agent.agent._load_existing", return_value=None),
        ):
            mock_loop.return_value = discovery_result
            await run_agent("m-2024", cheap_mode=cheap_mode, existing_data={})

            # The first call to _agent_loop should use the correct model
            call_kwargs = mock_loop.call_args_list[0]
            assert call_kwargs.kwargs["model"] == expected_model


@pytest.mark.asyncio
async def test_run_agent_custom_profile_preserved():
    """Custom profile uses balanced defaults but is recorded as custom."""
    discovery_result = {"id": "custom-2024", "candidates": []}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("custom-2024", model_profile="custom", existing_data={})

    assert mock_loop.call_args_list[0].kwargs["model"] == "google/gemini-2.5-flash"
    assert result["agent_metrics"]["model_profile"] == "custom"


@pytest.mark.asyncio
async def test_run_agent_respects_review_provider_selection():
    """Reviewer checkboxes should control which OpenRouter review roles run."""
    discovery_result = {"id": "reviewers-2024", "candidates": []}
    reviews = [{"model": "anthropic/claude-haiku-4.5", "verdict": "approved", "flags": []}]

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock) as mock_reviews,
    ):
        mock_loop.return_value = discovery_result
        mock_reviews.return_value = reviews
        result = await run_agent(
            "reviewers-2024",
            cheap_mode=True,
            existing_data={},
            enabled_steps=["discovery", "review"],
            review_providers=["claude"],
        )

    assert result["generator"] == [
        "deepseek/deepseek-v4-flash",
        "openai/gpt-5-nano",
        "anthropic/claude-haiku-4.5",
    ]
    assert mock_reviews.call_args.kwargs["review_providers"] == ["claude"]


@pytest.mark.asyncio
async def test_run_agent_default_iteration_rereviews_full_profile_once():
    discovery_result = {
        "id": "review-cycle-2026",
        "election_date": "2026-11-03",
        "candidates": [{"name": "Alice", "summary": "Before", "issues": {}}],
    }
    initial_reviews = [
        {
            "model": "claude",
            "verdict": "flagged",
            "score": 75,
            "flags": [{"field": "candidates[0].summary", "concern": "Needs detail", "severity": "warning"}],
        }
    ]
    final_reviews = [{"model": "claude", "verdict": "approved", "score": 95, "flags": []}]
    improved = {
        **discovery_result,
        "candidates": [{"name": "Alice", "summary": "After", "issues": {}}],
    }

    async def review_side_effect(_race_id, race_json, **kwargs):
        metrics = kwargs["metrics_sink"]
        metrics["whole_profile"] = True
        assert race_json["candidates"][0]["name"] == "Alice"
        return initial_reviews if not metrics.get("reviewed") else final_reviews

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, return_value=discovery_result),
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch(
            "pipeline_client.agent.agent._run_iteration_pass", new_callable=AsyncMock, return_value=improved
        ) as mock_iteration,
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock) as mock_reviews,
    ):

        async def tracked_reviews(*args, **kwargs):
            metrics = kwargs["metrics_sink"]
            result = await review_side_effect(*args, **kwargs)
            metrics["reviewed"] = True
            return result

        mock_reviews.side_effect = tracked_reviews
        result = await run_agent(
            "review-cycle-2026",
            existing_data={},
            enabled_steps=["discovery", "review", "iteration"],
        )

    assert mock_iteration.await_count == 1
    assert mock_reviews.await_count == 2
    assert "candidates[0].summary" in mock_reviews.call_args_list[1].kwargs["change_manifest"]
    assert mock_reviews.call_args_list[1].args[1]["candidates"][0]["summary"] == "After"
    assert result["agent_metrics"]["review"]["whole_profile"] is True


@pytest.mark.asyncio
async def test_run_agent_iteration_continuation_preserves_reviews_and_computes_grade():
    carried_reviews = [
        {
            "model": "claude",
            "verdict": "flagged",
            "score": 87,
            "flags": [{"field": "candidates[0].summary", "concern": "Needs detail", "severity": "warning"}],
        }
    ]
    existing = {
        "id": "review-continuation-2026",
        "election_date": "2026-11-03",
        "candidates": [{"name": "Alice", "summary": "Before", "issues": {}}],
        "reviews": carried_reviews,
        "pipeline_state": {"complete": True, "remaining_candidates": [], "remaining_steps": []},
        "agent_metrics": {"review": {"whole_profile": True, "packet_revisions": 1}},
    }
    improved = {
        **existing,
        "candidates": [{"name": "Alice", "summary": "After", "issues": {}}],
    }
    final_reviews = [{"model": "claude", "verdict": "approved", "score": 95, "flags": []}]

    with (
        patch(
            "pipeline_client.agent.agent._run_iteration_pass", new_callable=AsyncMock, return_value=improved
        ) as mock_iteration,
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock, return_value=final_reviews) as mock_reviews,
    ):
        result = await run_agent(
            "review-continuation-2026",
            existing_data=existing,
            enabled_steps=["iteration"],
            resume_partial=True,
        )

    assert mock_iteration.await_count == 1
    assert mock_iteration.call_args.args[2] == carried_reviews
    assert mock_reviews.await_count == 1
    assert result["reviews"] == final_reviews
    assert result["validation_grade"] == {
        "grade": "A",
        "score": 95,
        "passed": True,
        "summary": "Validated by 1/1 reviewers with an average score of 95/100.",
    }
    assert result["pipeline_state"]["complete"] is True


@pytest.mark.asyncio
async def test_iteration_pass_continuation_skips_completed_candidate_units():
    race = {
        "id": "iteration-units-2026",
        "candidates": [{"name": "Alice"}, {"name": "Bob"}],
        "pipeline_state": {"completed_units": ["iteration:1:Alice"]},
    }
    progress_updates = []

    with (
        patch("pipeline_client.agent.phases._candidate_source_hints", new_callable=AsyncMock, return_value=("", [])),
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, return_value={}) as mock_loop,
    ):
        result = await _run_iteration_pass(
            "iteration-units-2026",
            race,
            [{"model": "claude", "flags": [{"field": "summary", "severity": "warning"}]}],
            model="test-model",
            resume_partial=True,
            unit_prefix="iteration:1",
            on_progress=lambda pct, message, checkpoint: progress_updates.append((pct, message, checkpoint)),
        )

    assert result is not None
    phases = [call.kwargs["phase_name"] for call in mock_loop.call_args_list]
    assert phases == ["iterate-Bob", "iterate-meta"]
    assert set(result["pipeline_state"]["completed_units"]) >= {
        "iteration:1:Alice",
        "iteration:1:Bob",
    }
    assert progress_updates[-1][0] == 100
    assert progress_updates[-1][2]["pipeline_state"]["completed_units"] == result["pipeline_state"]["completed_units"]


@pytest.mark.asyncio
async def test_extra_review_cycles_require_error_flags(monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_REVIEW_CYCLES", "3")
    discovery_result = {
        "id": "review-errors-2026",
        "election_date": "2026-11-03",
        "candidates": [{"name": "Alice", "summary": "Before", "issues": {}}],
    }
    warning_reviews = [
        {
            "model": "claude",
            "verdict": "flagged",
            "score": 75,
            "flags": [{"field": "candidates[0].summary", "concern": "Needs detail", "severity": "warning"}],
        }
    ]

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, return_value=discovery_result),
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch(
            "pipeline_client.agent.agent._run_iteration_pass",
            new_callable=AsyncMock,
            return_value={**discovery_result, "candidates": [{"name": "Alice", "summary": "After", "issues": {}}]},
        ) as mock_iteration,
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock, return_value=warning_reviews) as mock_reviews,
    ):
        await run_agent(
            "review-errors-2026",
            existing_data={},
            enabled_steps=["discovery", "review", "iteration"],
        )

    assert mock_iteration.await_count == 1
    assert mock_reviews.await_count == 2


@pytest.mark.asyncio
async def test_run_agent_on_log_callback():
    """run_agent passes logs to the on_log callback."""
    discovery_result = {"id": "log-2024", "candidates": []}
    log_messages = []

    def on_log(level, msg):
        log_messages.append((level, msg))

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        await run_agent("log-2024", cheap_mode=True, existing_data={}, on_log=on_log)

    # Should have at least "New research" and "Agent finished" messages
    assert len(log_messages) >= 2
    assert any("New research" in msg for _, msg in log_messages)
    assert any("finished" in msg for _, msg in log_messages)
    assert all("ð" not in msg for _, msg in log_messages)


@pytest.mark.asyncio
async def test_run_agent_normalizes_new_fields():
    """run_agent sets defaults for image_url, career_history, education, voting_record."""
    discovery_result = {
        "id": "new-fields-2024",
        "candidates": [
            {
                "name": "Alice",
                "issues": {},
            }
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("new-fields-2024", cheap_mode=True, existing_data={})

    candidate = result["candidates"][0]
    assert candidate["image_url"] is None
    assert candidate["career_history"] == []
    assert candidate["education"] == []
    assert candidate["donor_summary"] is None
    assert candidate["donor_sources"] == []
    assert candidate["links"] == []


@pytest.mark.asyncio
async def test_run_agent_normalizes_schema_version_legacy_issues_and_missing_stances():
    """Final agent output should persist schema/default and issue migrations."""
    discovery_result = {
        "id": "normalize-2026",
        "schema_version": None,
        "election_date": "2026-11-03",
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Reproductive Rights": {
                        "stance": "Supports abortion access.",
                        "confidence": "high",
                        "sources": [],
                    },
                    "Abortion & Reproductive Health": {
                        "stance": "MISSING",
                        "confidence": "low",
                        "sources": [],
                    },
                    "Tech & AI": {
                        "stance": "MISSING",
                        "confidence": "low",
                        "sources": [],
                    },
                },
            }
        ],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "normalize-2026",
            cheap_mode=True,
            existing_data={},
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    issues = result["candidates"][0]["issues"]
    assert result["schema_version"] == "0.3"
    assert "Reproductive Rights" not in issues
    assert issues["Abortion & Reproductive Health"]["stance"] == "Supports abortion access."
    assert issues["Tech & AI"]["stance"] == "No public position found after repeated research attempts."


@pytest.mark.asyncio
async def test_run_agent_skips_reviews_when_step_disabled():
    """run_agent skips reviews when the review step is disabled."""
    discovery_result = {"id": "no-review-2024", "candidates": []}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "no-review-2024",
            cheap_mode=True,
            existing_data={},
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result.get("reviews") == []


@pytest.mark.asyncio
async def test_run_agent_defaults_house_ballotpedia_url_on_discovery_only():
    discovery_result = {
        "id": "ar-house-03-2026",
        "election_date": "2026-11-03",
        "candidates": [{"name": "Alice Smith"}],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("ar-house-03-2026", cheap_mode=True, existing_data={}, enabled_steps=["discovery"])

    assert result["ballotpedia_url"] == "https://ballotpedia.org/Arkansas'_3rd_Congressional_District"


@pytest.mark.asyncio
async def test_run_agent_review_skips_without_openrouter_key():
    """run_agent review step returns no reviews without an OpenRouter key."""
    discovery_result = {"id": "review-2024", "candidates": []}

    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch.dict(os.environ, env, clear=True),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("review-2024", cheap_mode=True, existing_data={})

    # No reviews because no OpenRouter key is set.
    assert result.get("reviews") == []


@pytest.mark.asyncio
async def test_run_agent_update_with_candidates():
    """run_agent in update mode with existing candidates runs roster sync + tools phases."""
    existing = {
        "id": "test-2024",
        "candidates": [{"name": "Alice", "party": "D", "issues": {}}],
        "updated_utc": "2024-01-01T00:00:00Z",
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        mock_loop.return_value = {}

        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["id"] == "test-2024"
    assert "updated_utc" in result
    # roster sync + roster verify + meta + images + 12 issues + finance + refine + meta refine = 19
    assert mock_loop.call_count == 19


def test_sanitize_roster_removes_incumbent_found_not_running():
    race_json = {
        "id": "mn-governor-2026",
        "candidates": [
            {
                "name": "Tim Walz",
                "party": "Democratic-Farmer-Labor",
                "incumbent": True,
                "summary": "Tim Walz is Minnesota's governor and announced he is not seeking re-election.",
                "summary_sources": [
                    {
                        "title": "Governor Walz Statement Announcing He Will Not Seek Reelection",
                        "url": "https://mn.gov/governor/newsroom/press-releases/?id=1055-718148",
                    }
                ],
            },
            {"name": "Jeff Johnson", "party": "Republican", "incumbent": False, "summary": "Declared candidate."},
        ],
    }

    _sanitize_roster(race_json)

    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Jeff Johnson"]


def test_sanitize_roster_removes_inactive_candidates_from_primary_or_withdrawal():
    race_json = {
        "id": "ar-governor-2026",
        "candidates": [
            {
                "name": "Pat Candidate",
                "party": "Republican",
                "incumbent": False,
                "summary": "Pat Candidate lost the Republican primary and did not advance to the general election.",
            },
            {
                "name": "Casey Former",
                "party": "Democratic",
                "incumbent": False,
                "summary": "Casey Former previously announced a campaign.",
                "withdrawn": True,
            },
            {
                "name": "Jordan Active",
                "party": "Republican",
                "incumbent": False,
                "summary": "Jordan Active is campaigning for the general election.",
            },
        ],
    }

    _sanitize_roster(race_json)

    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Jordan Active"]


def test_sanitize_roster_drops_malformed_candidate_entries():
    race_json = {
        "id": "ar-governor-2026",
        "candidates": [
            "not a candidate object",
            {"party": "Republican"},
            {"name": "  Sarah Huckabee Sanders  ", "party": "Republican"},
        ],
    }

    _sanitize_roster(race_json)

    assert race_json["candidates"] == [{"name": "Sarah Huckabee Sanders", "party": "Republican"}]


def test_authoritative_roster_removes_stale_primary_candidate():
    race_json = {
        "id": "ar-governor-2026",
        "candidates": [
            {"name": "Sarah Huckabee Sanders", "party": "Republican"},
            {"name": "Fred Love", "party": "Democratic"},
            {"name": "Colt Shelby", "party": "Libertarian"},
            {"name": "Supha Xayprasith-Mays", "party": "Democratic"},
        ],
    }

    _reconcile_candidates_with_authoritative_roster(
        race_json,
        [
            {"name": "Sarah Huckabee Sanders", "party": "Republican"},
            {"name": "Fredrick Love", "party": "Democratic"},
            {"name": "Colt Shelby", "party": "Libertarian"},
        ],
    )

    assert [candidate["name"] for candidate in race_json["candidates"]] == [
        "Sarah Huckabee Sanders",
        "Fred Love",
        "Colt Shelby",
    ]


def test_sanitize_roster_preserves_twenty_active_candidates():
    race_json = {
        "id": "crowded-primary-2026",
        "candidates": [
            {
                "name": f"Candidate {idx:02d}",
                "party": "Democratic" if idx % 2 else "Republican",
                "incumbent": False,
                "summary": "Declared candidate.",
            }
            for idx in range(1, 21)
        ],
    }

    _sanitize_roster(race_json)

    assert [candidate["name"] for candidate in race_json["candidates"]] == [f"Candidate {idx:02d}" for idx in range(1, 21)]
    assert "candidate_limit_note" not in race_json


def test_sanitize_polling_drops_non_roster_placeholder_poll():
    race_json = {
        "id": "ar-governor-2026",
        "candidates": [
            {"name": "Sarah Huckabee Sanders"},
            {"name": "Fred Love"},
            {"name": "Colt Shelby"},
        ],
        "polling": [
            {
                "pollster": "No new polls found",
                "date": "2026-04-06",
                "matchups": [
                    {
                        "candidates": [
                            "Sarah Huckabee Sanders",
                            "Fred Love",
                            "Colt Shelby",
                            "Supha Xayprasith-Mays",
                        ],
                        "percentages": [],
                    }
                ],
            }
        ],
    }

    _sanitize_polling(race_json)

    assert race_json["polling"] == []


def test_sanitize_polling_requires_exact_roster_names():
    race_json = {
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [
            {
                "pollster": "Example",
                "date": "2026-06-01",
                "matchups": [{"candidates": ["Alice", "Bob Jones"], "percentages": [48, 45]}],
            }
        ],
    }

    _sanitize_polling(race_json)

    assert race_json["polling"][0]["matchups"] == []


def test_sanitize_polling_keeps_source_only_polls_without_numeric_percentages():
    race_json = {
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [
            {
                "pollster": "Example",
                "date": "2026-06-01",
                "matchups": [{"candidates": ["Alice Smith", "Bob Jones"], "percentages": []}],
            },
            {
                "pollster": "Valid Poll",
                "date": "2026-06-02",
                "matchups": [{"candidates": ["Alice Smith", "Bob Jones"], "percentages": [48, 45]}],
            },
        ],
    }

    _sanitize_polling(race_json)

    assert [poll["pollster"] for poll in race_json["polling"]] == ["Example", "Valid Poll"]
    assert race_json["polling"][0]["matchups"] == []


@pytest.mark.asyncio
async def test_polling_step_runs_without_issue_finance_or_refinement():
    reviews = [
        {
            "model": "claude",
            "reviewed_at": "2026-06-01T00:00:00Z",
            "verdict": "approved",
            "score": 91,
            "flags": [],
            "summary": "Looks good.",
        }
    ]
    existing = {
        "id": "poll-only-2026",
        "election_date": "2026-11-03",
        "updated_utc": "2026-06-01T00:00:00Z",
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [],
        "reviews": reviews,
        "validation_grade": {
            "grade": "A",
            "score": 91,
            "passed": True,
            "summary": "Validated by 1/1 reviewers with an average score of 91/100.",
        },
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        result = await run_agent("poll-only-2026", existing_data=existing, enabled_steps=["polling"])

    assert mock_loop.await_count == 1
    assert mock_loop.call_args.kwargs["phase_name"] == "update-polling"
    tool_names = {tool["function"]["name"] for tool in mock_loop.call_args.kwargs["extra_tools"]}
    assert tool_names == {"add_poll", "remove_poll", "update_race_field", "read_profile"}
    assert result["candidates"][0]["name"] == "Alice Smith"
    assert result["reviews"] == reviews
    assert result["validation_grade"] == {
        "grade": "A",
        "score": 91,
        "passed": True,
        "summary": "Validated by 1/1 reviewers with an average score of 91/100.",
    }
    assert result["pipeline_state"]["complete"] is True
    assert result["pipeline_state"]["remaining_steps"] == []


@pytest.mark.asyncio
async def test_discovery_polling_forecast_refresh_does_not_require_review():
    existing = {
        "id": "market-refresh-2026",
        "election_date": "2026-11-03",
        "updated_utc": "2026-06-01T00:00:00Z",
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [],
        "pipeline_state": {"complete": True, "remaining_candidates": [], "remaining_steps": []},
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
        patch("pipeline_client.agent.phases.fetch_kalshi_market_signals", new_callable=AsyncMock, return_value=[]),
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        result = await run_agent(
            "market-refresh-2026",
            existing_data=existing,
            enabled_steps=["discovery", "polling", "forecast"],
        )

    assert mock_loop.await_count == 5
    assert result["pipeline_state"]["complete"] is True
    assert result["pipeline_state"]["remaining_steps"] == []


@pytest.mark.asyncio
async def test_voter_resources_step_runs_independently():
    existing = {
        "id": "resources-only-2026",
        "election_date": "2026-11-03",
        "updated_utc": "2026-06-01T00:00:00Z",
        "office": "Governor",
        "state": "Georgia",
        "candidates": [{"name": "Alice Smith"}],
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        await run_agent("resources-only-2026", existing_data=existing, enabled_steps=["voter_resources"])

    assert mock_loop.await_count == 1
    assert mock_loop.call_args.kwargs["phase_name"] == "update-voter-resources"
    tool = mock_loop.call_args.kwargs["extra_tools"][0]
    assert tool["function"]["parameters"]["properties"]["field"]["enum"] == [
        "ballotpedia_url",
        "register_to_vote_url",
        "how_to_vote_url",
    ]


@pytest.mark.asyncio
async def test_run_agent_continuation_skips_completed_issue_stances():
    """Continuation mode resumes issue research at the next missing issue."""
    existing = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "party": "D",
                "issues": {
                    CANONICAL_ISSUES[0]: {
                        "issue": CANONICAL_ISSUES[0],
                        "stance": "Existing stance",
                        "confidence": "high",
                        "sources": [],
                    }
                },
            }
        ],
        "updated_utc": "2024-01-01T00:00:00Z",
    }

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = {}

        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            resume_partial=True,
        )

    assert result["candidates"][0]["issues"][CANONICAL_ISSUES[0]]["stance"] == "Existing stance"
    assert mock_loop.call_count == len(CANONICAL_ISSUES) - 1


@pytest.mark.asyncio
async def test_run_agent_continuation_retries_blank_issue_stances():
    existing = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "party": "D",
                "issues": {
                    CANONICAL_ISSUES[0]: {
                        "issue": CANONICAL_ISSUES[0],
                        "stance": "",
                        "confidence": "low",
                        "sources": [],
                    }
                },
            }
        ],
        "pipeline_state": {
            "completed_units": [f"issues:Alice:{CANONICAL_ISSUES[0]}"],
        },
        "updated_utc": "2024-01-01T00:00:00Z",
    }

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = {}
        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            resume_partial=True,
        )

    assert mock_loop.call_count == len(CANONICAL_ISSUES)
    assert f"issues:Alice:{CANONICAL_ISSUES[0]}" not in result["pipeline_state"]["completed_units"]


@pytest.mark.asyncio
async def test_run_agent_continuation_caps_repeated_issue_attempts(monkeypatch):
    capped_issue = CANONICAL_ISSUES[0]
    completed_issues = {
        issue: {
            "issue": issue,
            "stance": f"Existing stance on {issue}",
            "confidence": "high",
            "sources": [],
        }
        for issue in CANONICAL_ISSUES[1:]
    }
    existing = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "party": "D",
                "issues": {
                    capped_issue: {"issue": capped_issue, "stance": "", "confidence": "low", "sources": []},
                    **completed_issues,
                },
            }
        ],
        "pipeline_state": {
            "completed_units": [f"issues:Alice:{issue}" for issue in CANONICAL_ISSUES],
            "issue_attempts": {f"issues:Alice:{capped_issue}": 3},
        },
        "updated_utc": "2024-01-01T00:00:00Z",
    }
    monkeypatch.setenv("PIPELINE_ISSUE_MAX_ATTEMPTS", "3")

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            resume_partial=True,
        )

    assert mock_loop.call_count == 0
    assert "repeated research attempts" in result["candidates"][0]["issues"][capped_issue]["stance"]
    assert f"issues:Alice:{capped_issue}" in result["pipeline_state"]["completed_units"]


@pytest.mark.asyncio
async def test_run_agent_continuation_skips_completed_refinement_units():
    existing = {
        "id": "test-2026",
        "election_date": "2026-11-03",
        "office": "Governor",
        "state": "Michigan",
        "candidates": [
            {"name": "Alice", "party": "D", "issues": {}},
            {"name": "Bob", "party": "R", "issues": {}},
        ],
        "pipeline_state": {"completed_units": ["refinement:Alice"]},
        "updated_utc": "2026-01-01T00:00:00Z",
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._candidate_source_hints", new_callable=AsyncMock, return_value=("", [])),
    ):
        result = await run_agent(
            "test-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["refinement"],
            resume_partial=True,
        )

    phase_names = [call.kwargs["phase_name"] for call in mock_loop.call_args_list]
    assert phase_names == ["upd-refine-Bob", "upd-refine-meta"]
    assert "refinement:Alice" in result["pipeline_state"]["completed_units"]
    assert "refinement:Bob" in result["pipeline_state"]["completed_units"]
    assert "refinement:meta" in result["pipeline_state"]["completed_units"]


@pytest.mark.asyncio
async def test_run_agent_continuation_does_not_report_skipped_issue_as_active():
    """Skipped checkpointed issue stances should not look like active research."""
    existing = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "party": "D",
                "issues": {
                    CANONICAL_ISSUES[0]: {
                        "issue": CANONICAL_ISSUES[0],
                        "stance": "Existing stance",
                        "confidence": "high",
                        "sources": [],
                    }
                },
            }
        ],
        "updated_utc": "2024-01-01T00:00:00Z",
    }
    active_messages = []
    checkpoint_messages = []

    def _progress(step: str, **kwargs):
        if step != "issues":
            return
        message = kwargs.get("message", "")
        if message.startswith("Issues ·"):
            active_messages.append(message)
        if message.startswith("Issues checkpoint"):
            checkpoint_messages.append(message)

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = {}

        await run_agent(
            "test-2024",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            step_tracker={"progress": _progress},
            resume_partial=True,
        )

    assert all(CANONICAL_ISSUES[0] not in message for message in active_messages)
    assert any(CANONICAL_ISSUES[0] in message for message in checkpoint_messages)
    assert mock_loop.call_count == len(CANONICAL_ISSUES) - 1


@pytest.mark.asyncio
async def test_issue_research_uses_bounded_isolated_concurrency(monkeypatch):
    existing = {
        "id": "test-2026",
        "election_date": "2026-11-03",
        "candidates": [
            {"name": "Alice", "party": "D", "issues": {}},
            {"name": "Bob", "party": "R", "issues": {}},
        ],
        "updated_utc": "2026-01-01T00:00:00Z",
    }
    active = 0
    max_active = 0

    async def fake_loop(_system, user, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.005)
        candidate = re.search(r"^Candidate: (.+)$", user, re.MULTILINE).group(1)
        issue = re.search(r"^Issue to (?:research|update): (.+)$", user, re.MULTILINE).group(1)
        kwargs["extra_tool_handlers"]["set_issue_stance"](
            {
                "candidate_name": candidate,
                "issue": issue,
                "stance": f"{candidate} stance on {issue}",
                "confidence": "low",
                "sources": [],
            }
        )
        active -= 1
        return {}

    monkeypatch.setenv("PIPELINE_ISSUE_CONCURRENCY", "2")
    with (
        patch("pipeline_client.agent.phases._agent_loop", side_effect=fake_loop),
        patch("pipeline_client.agent.phases._candidate_source_hints", new_callable=AsyncMock, return_value=("", [])),
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        result = await run_agent(
            "test-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
        )

    assert 1 < max_active <= 2
    assert all(len(candidate["issues"]) == len(CANONICAL_ISSUES) for candidate in result["candidates"])


@pytest.mark.asyncio
async def test_candidate_batches_resume_from_durable_issue_units():
    existing = {
        "id": "test-2026",
        "election_date": "2026-11-03",
        "candidates": [
            {"name": "Alice", "party": "D", "issues": {}},
            {"name": "Bob", "party": "R", "issues": {}},
        ],
        "updated_utc": "2026-01-01T00:00:00Z",
    }

    async def fake_loop(_system, user, **kwargs):
        candidate = re.search(r"^Candidate: (.+)$", user, re.MULTILINE).group(1)
        issue = re.search(r"^Issue to (?:research|update): (.+)$", user, re.MULTILINE).group(1)
        kwargs["extra_tool_handlers"]["set_issue_stance"](
            {
                "candidate_name": candidate,
                "issue": issue,
                "stance": f"{candidate} stance on {issue}",
                "confidence": "low",
                "sources": [],
            }
        )
        return {}

    common_patches = (
        patch("pipeline_client.agent.phases._agent_loop", side_effect=fake_loop),
        patch("pipeline_client.agent.phases._candidate_source_hints", new_callable=AsyncMock, return_value=("", [])),
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    )
    with common_patches[0], common_patches[1], common_patches[2]:
        first = await run_agent(
            "test-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            max_candidates=1,
        )

    assert first["pipeline_state"]["remaining_candidates"] == ["Bob"]
    assert len(first["candidates"][0]["issues"]) == len(CANONICAL_ISSUES)
    assert first["candidates"][1]["issues"] == {}

    with (
        patch("pipeline_client.agent.phases._agent_loop", side_effect=fake_loop),
        patch("pipeline_client.agent.phases._candidate_source_hints", new_callable=AsyncMock, return_value=("", [])),
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        resumed = await run_agent(
            "test-2026",
            cheap_mode=True,
            existing_data=first,
            enabled_steps=["issues"],
            max_candidates=1,
            resume_partial=True,
        )

    assert resumed["pipeline_state"]["remaining_candidates"] == []
    assert all(len(candidate["issues"]) == len(CANONICAL_ISSUES) for candidate in resumed["candidates"])


@pytest.mark.asyncio
async def test_issue_checkpoint_progress_includes_partial_race_json():
    """Issue checkpoints send the mutated RaceJSON to the handler for handoff storage."""
    existing = {
        "id": "test-2024",
        "candidates": [{"name": "Alice", "party": "D", "issues": {}}],
        "updated_utc": "2024-01-01T00:00:00Z",
    }
    progress_payloads = []

    def _progress(step: str, **kwargs):
        if step == "issues" and "race_json" in kwargs and kwargs.get("message", "").startswith("Issues checkpoint"):
            progress_payloads.append(kwargs["race_json"])

    async def fake_loop(_system, user, **kwargs):
        candidate = re.search(r"^Candidate: (.+)$", user, re.MULTILINE).group(1)
        issue = re.search(r"^Issue to (?:research|update): (.+)$", user, re.MULTILINE).group(1)
        kwargs["extra_tool_handlers"]["set_issue_stance"](
            {
                "candidate_name": candidate,
                "issue": issue,
                "stance": f"{candidate} stance on {issue}",
                "confidence": "low",
                "sources": [],
            }
        )
        return {}

    with patch("pipeline_client.agent.phases._agent_loop", side_effect=fake_loop):
        await run_agent(
            "test-2024",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            step_tracker={"progress": _progress},
        )

    assert len(progress_payloads) == len(CANONICAL_ISSUES)
    assert progress_payloads[-1]["id"] == "test-2024"
