from pipeline_client.agent.model_registry import DEFAULT_RESEARCH_MODEL, PREMIUM_RESEARCH_MODEL, SMALL_MODEL

"""Tests for run_agent orchestration and _load_existing helper."""

import asyncio
import copy
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from pipeline_client.agent.agent import (
    _clear_stale_iteration_checkpoints,
    _load_existing,
    _normalize_schema_fields,
    _sanitize_polling,
    run_agent,
)
from pipeline_client.agent.phases import (
    _add_candidates_from_authoritative_roster,
    _format_review_flags,
    _reconcile_candidates_with_authoritative_roster,
    _run_iteration_pass,
    _sanitize_roster,
)
from pipeline_client.agent.phases.update_run import _fast_probe_baseline_reason, _metadata_fast_probe_allowed
from pipeline_client.agent.prompts import CANONICAL_ISSUES
from pipeline_client.agent.run_budget import RunBudget, RunBudgetExceeded
from pipeline_client.backend.handlers.agent import HandoffTriggered
from shared.models import RaceJSON
from shared.pipeline_config import PIPELINE_STEP_IDS


@pytest.fixture(autouse=True)
def no_openrouter_key(monkeypatch):
    """Unit tests mock agent phases; never call real OpenRouter reviews."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def _race_with_finalized_roster(*, stage="post_primary_general", finalized_at=None):
    finalized_at = finalized_at or datetime.now(timezone.utc).isoformat()
    source = {
        "url": "https://elections.example.gov/contest",
        "type": "official",
        "title": "Certified candidates",
        "evidence": "Alice Example and Bob Example are certified candidates.",
        "last_accessed": finalized_at,
        "race_id": "xy-house-01-2026",
        "evidence_tier": 1,
        "retrieval_status": "content",
    }
    return {
        "id": "xy-house-01-2026",
        "election_date": "2026-11-03",
        "updated_utc": finalized_at,
        "contest_stage": stage,
        "candidates": [
            {"name": "Alice Example", "party": "Democratic", "roster_sources": [source]},
            {"name": "Bob Example", "party": "Republican", "roster_sources": [source]},
        ],
        "pipeline_state": {
            "complete": True,
            "remaining_candidates": [],
            "remaining_steps": [],
            "completed_units": [],
            "roster_research": {
                "finalized_at": finalized_at,
                "contest_stage": stage,
                "summary": "Certified field",
                "active_candidate_count": 2,
                "candidate_names": ["Alice Example", "Bob Example"],
                "completeness_sources": [source],
            },
            "metadata_research": {
                "finalized_at": finalized_at,
                "active_candidate_count": 2,
                "description_sources": [source],
                "candidate_sources": {"Alice Example": [source], "Bob Example": [source]},
            },
        },
        "run_health": {"status": "healthy", "reasons": []},
    }


def test_recent_finalized_roster_allows_fast_probe_at_same_known_stage():
    race = _race_with_finalized_roster()
    assert _fast_probe_baseline_reason(race, max_age_days=90)

    race["contest_stage"] = "pre_primary"
    assert _fast_probe_baseline_reason(race, max_age_days=90) is None


@pytest.mark.parametrize("stage", ["pre_primary", "runoff", "special"])
def test_known_roster_stages_can_use_current_change_probe(stage):
    assert _fast_probe_baseline_reason(_race_with_finalized_roster(stage=stage), max_age_days=90)


def test_unknown_roster_stage_cannot_use_fast_probe():
    assert _fast_probe_baseline_reason(_race_with_finalized_roster(stage="unknown"), max_age_days=90) is None


def test_new_run_clears_stale_iteration_checkpoints_before_a_handoff():
    race = {
        "pipeline_state": {
            "completed_units": [
                "issues:Alice:Economy",
                "iteration:1:Alice",
                "iteration:2:Bob",
                "refinement:Alice",
            ]
        }
    }

    _clear_stale_iteration_checkpoints(race)

    assert race["pipeline_state"]["completed_units"] == [
        "issues:Alice:Economy",
        "refinement:Alice",
    ]


def test_stale_unproven_or_stage_mismatched_roster_is_not_reused():
    stale = _race_with_finalized_roster(finalized_at=(datetime.now(timezone.utc) - timedelta(days=91)).isoformat())
    assert _fast_probe_baseline_reason(stale, max_age_days=90) is None

    unproven = _race_with_finalized_roster()
    unproven["pipeline_state"]["roster_research"]["completeness_status"] = "unproven"
    assert _fast_probe_baseline_reason(unproven, max_age_days=90) is None

    mismatched = _race_with_finalized_roster()
    mismatched["pipeline_state"]["roster_research"]["contest_stage"] = "pre_primary"
    assert _fast_probe_baseline_reason(mismatched, max_age_days=90) is None

    changed_names = _race_with_finalized_roster()
    changed_names["candidates"][1]["name"] = "Different Candidate"
    assert _fast_probe_baseline_reason(changed_names, max_age_days=90) is None


def test_stale_metadata_cannot_use_fast_probe():
    race = _race_with_finalized_roster()
    race["pipeline_state"]["metadata_research"]["finalized_at"] = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    assert _metadata_fast_probe_allowed(race, max_age_days=90) is False


@pytest.mark.asyncio
async def test_update_fast_paths_unchanged_roster_and_metadata():
    existing = _race_with_finalized_roster()

    async def fast_no_change(*_args, **kwargs):
        assert kwargs["allow_no_change_after_search"] is True
        return {"_tool_trace": {"no_change_confirmed": True}}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock) as ballotpedia,
    ):
        mock_loop.side_effect = fast_no_change
        result = await run_agent(
            "xy-house-01-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
            allow_fast_no_change=True,
        )

    ballotpedia.assert_awaited_once()
    assert [call.kwargs.get("phase_name") for call in mock_loop.call_args_list] == ["roster-sync", "update-meta"]
    assert set(result["pipeline_state"]["skipped_units"]) == {
        "discovery.roster_sync",
        "discovery.roster_verify",
        "discovery.metadata",
    }


@pytest.mark.asyncio
async def test_roster_change_disables_metadata_fast_path_and_clears_old_skip_markers():
    existing = _race_with_finalized_roster()
    existing["pipeline_state"]["skipped_units"] = [
        "discovery.roster_sync",
        "discovery.roster_verify",
        "discovery.metadata",
    ]

    async def run_phase(*_args, **kwargs):
        if kwargs["phase_name"] == "roster-sync":
            existing["candidates"][1]["name"] = "Carol Replacement"
            return {"_tool_trace": {"required_final_tool_succeeded": True}}
        if kwargs["phase_name"] == "update-meta":
            assert kwargs["allow_no_change_after_search"] is False
        return {"_tool_trace": {}}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, side_effect=run_phase),
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        result = await run_agent(
            "xy-house-01-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
            allow_fast_no_change=True,
        )

    assert result["pipeline_state"]["skipped_units"] == []


# ---------------------------------------------------------------------------
# Load existing data tests
# ---------------------------------------------------------------------------


def test_load_existing_returns_none_for_missing():
    """_load_existing returns None when no published file exists."""
    result = _load_existing("nonexistent-race-9999")
    assert result is None


def test_sanitize_candidate_issues_normalizes_placeholder_variant():
    """_sanitize_candidate_issues must catch placeholder variants like 'To be
    determined after review', not just the bare exact marker — this is the
    safety net that should have caught the literal placeholder that shipped
    in a published race before this fix."""
    from pipeline_client.agent.agent import _sanitize_candidate_issues

    race_json = {
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Civil Rights & Equality": {
                        "issue": "Civil Rights & Equality",
                        "stance": "To be determined after review",
                        "confidence": "low",
                        "sources": [{"url": "https://example.com/podcast"}],
                    }
                },
            }
        ]
    }

    _sanitize_candidate_issues(race_json, log=None)

    stance = race_json["candidates"][0]["issues"]["Civil Rights & Equality"]
    assert stance["stance"] == ""


def test_sanitize_candidate_issues_removes_noncanonical_and_malformed_duplicates():
    from pipeline_client.agent.agent import _sanitize_candidate_issues

    race_json = {
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Economy": {
                        "issue": "Economy",
                        "stance": "Canonical researched position.",
                        "confidence": "high",
                        "sources": [],
                    },
                    "economy": "legacy malformed duplicate",
                    "family_values": "noncanonical legacy value",
                },
            }
        ]
    }

    _sanitize_candidate_issues(race_json, log=None)

    assert list(race_json["candidates"][0]["issues"]) == ["Economy"]


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


def test_format_review_flags_can_scope_to_one_candidate():
    reviews = [
        {
            "model": "automated-profile-quality",
            "verdict": "flagged",
            "summary": "Found profile issues.",
            "flags": [
                {
                    "field": "candidates[0].summary_sources[0].url",
                    "concern": "Alice source is stale.",
                    "severity": "warning",
                },
                {
                    "field": "candidates[1].issues.Healthcare.sources[0].url",
                    "concern": "Bob source is dead.",
                    "severity": "warning",
                },
                {
                    "field": "candidates[3].links[0].url",
                    "concern": "Source for Alice Example is duplicated.",
                    "severity": "info",
                },
                {
                    "field": "description",
                    "concern": "Race description is too short.",
                    "severity": "error",
                },
            ],
        }
    ]

    result = _format_review_flags(reviews, candidate_index=0, candidate_name="Alice Example", include_global=False)

    assert "Alice source is stale" in result
    assert "Source for Alice Example is duplicated" in result
    assert "Bob source is dead" not in result
    assert "Race description is too short" not in result


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


def test_normalize_schema_fields_clamps_invalid_roster_source_type():
    """An out-of-enum roster_sources[].type (e.g. 'website', written directly by
    discovery rather than through the roster-sources tool) must be clamped to
    'other' *before* Pydantic validation — otherwise validation raises, the
    exception is swallowed, and the raw invalid document ships unmigrated."""
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
                "roster_sources": [
                    {"url": "https://example.com/a", "type": "website"},
                    {"url": "https://example.com/b", "type": "official"},
                ],
            }
        ],
    }

    _normalize_schema_fields(race_json, lambda *_: None)

    types = [s["type"] for s in race_json["candidates"][0]["roster_sources"]]
    assert types == ["other", "official"]


def test_normalize_schema_fields_converts_blank_optional_source_dates_to_none():
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
                "voting_sources": [
                    {
                        "url": "https://example.com/alice",
                        "type": "website",
                        "last_accessed": "2026-08-21T00:00:00Z",
                        "published_at": "  ",
                    }
                ],
            }
        ],
    }
    messages = []

    _normalize_schema_fields(race_json, lambda level, message: messages.append((level, message)))

    assert race_json["candidates"][0]["voting_sources"][0]["published_at"] is None
    assert messages == [("warning", "Normalized 1 blank optional source published_at value(s)")]


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
    assert result["generator"] == [DEFAULT_RESEARCH_MODEL, SMALL_MODEL]
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
async def test_run_agent_breaks_exact_cost_into_llm_and_search_components():
    discovery_result = {"id": "cost-components-2026", "candidates": [{"name": "Alice", "issues": {}}]}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "cost-components-2026",
            cheap_mode=True,
            enabled_steps=["discovery"],
            prior_agent_metrics={
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "provider_cost_usd": 0.00123,
                "priced_calls": 2,
                "unpriced_calls": 0,
                "serper_calls": 3,
                "model_breakdown": {"openai/gpt-5.4-mini": {"prompt_tokens": 100, "completion_tokens": 20}},
            },
        )

    metrics = result["agent_metrics"]
    assert metrics["llm_cost_usd"] == pytest.approx(0.00123)
    assert metrics["search_cost_usd"] == pytest.approx(0.003)
    assert metrics["cost_usd"] == pytest.approx(metrics["llm_cost_usd"] + metrics["search_cost_usd"])


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
async def test_run_agent_caps_oversized_fresh_roster():
    """Oversized rosters are hard-capped to 8, balanced across major parties."""
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

    parties = [candidate["party"] for candidate in result["candidates"]]
    assert len(result["candidates"]) == 8
    assert parties.count("Democratic") == 4
    assert parties.count("Republican") == 4
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
        mock_loop.side_effect = [{"_tool_trace": {"required_final_tool_succeeded": True}}, {}, {}]
        await run_agent(
            "al-senate-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
            goal="Use the certified special-election roster.",
        )

    assert [call.kwargs["phase_name"] for call in mock_loop.call_args_list] == [
        "roster-sync",
        "roster-verify",
        "update-meta",
    ]
    assert "Use the certified special-election roster." in mock_loop.call_args_list[0].args[1]


@pytest.mark.asyncio
async def test_unproven_roster_completeness_keeps_going_and_says_so():
    existing = {
        "id": "al-house-02-2026",
        "election_date": "2026-11-03",
        "candidates": [
            {"name": "Wrong Contest", "party": "Unknown", "roster_sources": []},
            {"name": "Supported Candidate", "party": "Unknown", "roster_sources": []},
        ],
        "updated_utc": "2026-01-01T00:00:00Z",
    }

    async def fail_roster_finalization(*_args, **kwargs):
        if kwargs.get("phase_name") == "roster-verify":
            kwargs["extra_tool_handlers"]["remove_candidate"](
                {"name": "Wrong Contest", "reason": "Officially withdrew from the race."}
            )
        return {"_tool_trace": {"required_final_tool_succeeded": False}}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        mock_loop.side_effect = fail_roster_finalization
        result = await run_agent(
            "al-house-02-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery", "images", "polling", "forecast"],
        )

    # Unproven completeness is an honest partial, not a broken run: the roster we
    # hold is kept and flagged, downstream steps still run (bailing here left the
    # race stale AND silent about why), and health degrades rather than fails.
    assert mock_loop.await_count > 1
    assert result["pipeline_state"]["complete"] is False
    # Discovery ran and reached a conclusion, so it is not "still to do". Saying
    # otherwise blocked publication of races whose rosters were correct — the
    # publish gate tolerates a pending review and nothing else.
    assert "discovery" not in (result["pipeline_state"].get("remaining_steps") or [])
    assert result["run_health"]["status"] == "degraded"
    roster_research = result["pipeline_state"]["roster_research"]
    assert roster_research["finalized_at"]
    assert roster_research["summary"] == roster_research["completeness_note"]
    assert roster_research["completeness_status"] == "unproven"
    assert "could not confirm the complete candidate field" in roster_research["completeness_note"].lower()
    assert [candidate["name"] for candidate in result["candidates"]] == ["Supported Candidate"]
    assert roster_research["active_candidate_count"] == len(result["candidates"])
    RaceJSON.model_validate(result)
    reasons = result["run_health"]["reasons"]
    assert "roster_completeness_unproven" in reasons


@pytest.mark.asyncio
async def test_roster_verify_can_recover_completeness_after_removing_primary_losers():
    existing = {
        "id": "al-house-02-2026",
        "election_date": "2026-11-03",
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic", "roster_sources": []},
            {"name": "Rhett Marques", "party": "Republican", "roster_sources": []},
            {"name": "Primary Loser", "party": "Republican", "roster_sources": []},
        ],
        "updated_utc": "2026-08-01T00:00:00Z",
    }

    async def recover_in_verify(*args, **kwargs):
        if kwargs.get("phase_name") == "roster-sync":
            return {"_tool_trace": {"required_final_tool_succeeded": False}}
        if kwargs.get("phase_name") == "roster-verify":
            assert kwargs["required_final_tool_name"] == "finalize_roster"
            recovery_tools = {tool["function"]["name"] for tool in kwargs["extra_tools"]}
            assert {"set_race_identity", "finalize_roster"}.issubset(recovery_tools)
            assert "Call set_race_identity" in args[1]
            assert "Any candidates added during the sync that were NOT in the original list:\n(none)" in args[1]
            kwargs["extra_tool_handlers"]["remove_candidate"](
                {"name": "Primary Loser", "reason": "Lost the completed special primary."}
            )
            return {"_tool_trace": {"required_final_tool_succeeded": True}}
        return {}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        mock_loop.side_effect = recover_in_verify
        result = await run_agent(
            "al-house-02-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
            candidate_names=["Shomari Figures"],
        )

    assert [candidate["name"] for candidate in result["candidates"]] == ["Shomari Figures", "Rhett Marques"]
    assert "roster_completeness_unproven" not in result["run_health"]["reasons"]
    assert (result["pipeline_state"].get("roster_research") or {}).get("completeness_status") != "unproven"
    assert result["pipeline_state"]["complete"] is True


@pytest.mark.asyncio
async def test_roster_completeness_recovery_survives_continuation_checkpoint():
    existing = {
        "id": "al-house-02-2026",
        "election_date": "2026-11-03",
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic", "roster_sources": []},
            {"name": "Rhett Marques", "party": "Republican", "roster_sources": []},
        ],
        "pipeline_state": {
            "complete": True,
            "remaining_candidates": [],
            "remaining_steps": [],
            "completed_units": ["discovery.roster_sync"],
            "roster_finalization_pending": True,
            "roster_sync_original_names": ["Shomari Figures"],
        },
        "updated_utc": "2026-08-12T00:00:00Z",
    }

    async def finish_recovery(*_args, **kwargs):
        if kwargs.get("phase_name") == "roster-verify":
            assert kwargs["required_final_tool_name"] == "finalize_roster"
            assert "Any candidates added during the sync that were NOT in the original list:\nRhett Marques" in _args[1]
            return {"_tool_trace": {"required_final_tool_succeeded": True}}
        return {}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        mock_loop.side_effect = finish_recovery
        result = await run_agent(
            "al-house-02-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
            resume_partial=True,
        )

    assert [call.kwargs["phase_name"] for call in mock_loop.call_args_list] == ["roster-verify", "update-meta"]
    assert "roster_finalization_pending" not in result["pipeline_state"]
    assert "roster_sync_original_names" not in result["pipeline_state"]
    assert "roster_completeness_unproven" not in result["run_health"]["reasons"]
    assert result["pipeline_state"]["complete"] is True


@pytest.mark.asyncio
async def test_failed_roster_sync_writes_recovery_state_before_checkpoint():
    existing = {
        "id": "al-house-02-2026",
        "election_date": "2026-11-03",
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic", "roster_sources": []},
            {"name": "Rhett Marques", "party": "Republican", "roster_sources": []},
        ],
        "updated_utc": "2026-08-12T00:00:00Z",
    }
    checkpoint = {}

    def capture_checkpoint(step, **kwargs):
        race_json = kwargs.get("race_json") or {}
        state = race_json.get("pipeline_state") or {}
        if step == "discovery" and state.get("roster_finalization_pending") is True:
            checkpoint.update(copy.deepcopy(state))
            raise HandoffTriggered("continuation-item", ["discovery"], "continuation-run")

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        mock_loop.return_value = {"_tool_trace": {"required_final_tool_succeeded": False}}
        with pytest.raises(HandoffTriggered):
            await run_agent(
                "al-house-02-2026",
                cheap_mode=True,
                existing_data=existing,
                enabled_steps=["discovery"],
                step_tracker={"progress": capture_checkpoint},
            )

    assert checkpoint["roster_finalization_pending"] is True
    assert checkpoint["roster_sync_original_names"] == ["Shomari Figures", "Rhett Marques"]


@pytest.mark.asyncio
async def test_advisory_roster_timeout_does_not_checkpoint_stale_completed_units():
    existing = {
        "id": "ak-governor-2026",
        "election_date": "2026-11-03",
        "candidates": [{"name": "Candidate One", "party": "Independent", "roster_sources": []}],
        "pipeline_state": {
            "complete": True,
            "remaining_candidates": [],
            "remaining_steps": [],
            "completed_units": ["discovery.roster_sync", "discovery.roster_verify", "discovery.metadata"],
        },
        "updated_utc": "2026-08-12T00:00:00Z",
    }

    async def advisory_timeout(*_args, **_kwargs):
        raise RunBudgetExceeded("Ballotpedia roster sync exceeded the remaining run budget")

    async def inspect_cleared_checkpoint(*_args, **kwargs):
        if kwargs.get("phase_name") == "roster-sync":
            units = set((existing.get("pipeline_state") or {}).get("completed_units") or [])
            assert not units.intersection({"discovery.roster_sync", "discovery.roster_verify", "discovery.metadata"})
            return {"_tool_trace": {"required_final_tool_succeeded": True}}
        return {}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", side_effect=advisory_timeout),
    ):
        mock_loop.side_effect = inspect_cleared_checkpoint
        result = await run_agent(
            "ak-governor-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
            run_budget=RunBudget(deadline_at=time.time() + 3600),
        )

    assert any(call.kwargs.get("phase_name") == "roster-sync" for call in mock_loop.call_args_list)
    assert result["run_health"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_fresh_run_continues_after_advisory_roster_timeout():
    discovered = {
        "id": "ak-governor-2026",
        "election_date": "2026-11-03",
        "candidates": [{"name": "Candidate One", "party": "Independent", "roster_sources": []}],
    }

    async def advisory_timeout(*_args, **_kwargs):
        raise RunBudgetExceeded("Ballotpedia roster sync exceeded the remaining run budget")

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, return_value=discovered),
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", side_effect=advisory_timeout),
    ):
        result = await run_agent(
            "ak-governor-2026",
            cheap_mode=True,
            existing_data={},
            enabled_steps=["discovery"],
            run_budget=RunBudget(deadline_at=time.time() + 3600),
        )

    assert [candidate["name"] for candidate in result["candidates"]] == ["Candidate One"]
    assert result["run_health"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_successful_roster_recovery_clears_initial_sync_error():
    existing = {
        "id": "ar-supreme-court-2026",
        "election_date": "2026-03-03",
        "candidates": [
            {"name": "Nicholas Bronni", "party": "Nonpartisan", "roster_sources": []},
            {"name": "John Adams", "party": "Nonpartisan", "roster_sources": []},
        ],
        "updated_utc": "2026-01-01T00:00:00Z",
    }

    async def recover_after_error(*_args, **kwargs):
        if kwargs.get("phase_name") == "roster-sync":
            raise RuntimeError("temporary provider error")
        if kwargs.get("phase_name") == "roster-verify":
            return {"_tool_trace": {"required_final_tool_succeeded": True}}
        return {}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
    ):
        mock_loop.side_effect = recover_after_error
        result = await run_agent(
            "ar-supreme-court-2026",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["discovery"],
        )

    assert result["run_health"]["status"] == "healthy"
    assert result["pipeline_state"]["step_failures"] == []


@pytest.mark.asyncio
async def test_run_agent_defaults_existing_profile_to_low_cost_update_steps():
    existing = {
        "id": "maintenance-2026",
        "candidates": [{"name": "Alice", "issues": {}}],
        "updated_utc": "2026-07-20T00:00:00Z",
    }
    observed = {}

    async def fake_update(*_args, step_enabled, **_kwargs):
        for step in PIPELINE_STEP_IDS:
            observed[step] = step_enabled(step)
        return copy.deepcopy(existing)

    with (
        patch("pipeline_client.agent.agent._run_update", side_effect=fake_update),
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock) as mock_reviews,
    ):
        await run_agent("maintenance-2026", cheap_mode=True, existing_data=existing)

    assert observed["discovery"] is True
    assert observed["voter_resources"] is True
    assert observed["issues"] is False
    assert observed["review"] is False
    assert observed["iteration"] is False
    mock_reviews.assert_not_awaited()


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
    assert result["generator"] == [DEFAULT_RESEARCH_MODEL, SMALL_MODEL]
    assert result["contest_stage"] == "unknown"
    assert result["run_audit"]["contest_stage"] == "unknown"
    assert "No roster membership changes detected." in result["run_audit"]["candidate_changes"]


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
    """run_agent selects the configured primary model for each profile.

    An unset cheap_mode resolves to `default` rather than to a middle tier: the
    middle profile it used to select was both weaker and dearer than `default`.
    """
    discovery_result = {"id": "m-2024", "candidates": []}

    cases = [
        (True, DEFAULT_RESEARCH_MODEL),
        (False, PREMIUM_RESEARCH_MODEL),
        (None, DEFAULT_RESEARCH_MODEL),
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
    """Custom profile falls back to `default` models but is recorded as custom."""
    discovery_result = {"id": "custom-2024", "candidates": []}

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("custom-2024", model_profile="custom", existing_data={})

    assert mock_loop.call_args_list[0].kwargs["model"] == DEFAULT_RESEARCH_MODEL
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
        DEFAULT_RESEARCH_MODEL,
        SMALL_MODEL,
        "anthropic/claude-haiku-4.5",
    ]
    assert mock_reviews.call_args.kwargs["review_providers"] == ["claude"]


@pytest.mark.asyncio
async def test_run_agent_cleans_legacy_optional_values_before_review():
    discovery_result = {
        "id": "cleanup-before-review-2026",
        "candidates": [{"name": "Alice", "issues": {}, "social_media": {"linkedin": None}}],
    }
    reviews = [{"model": "claude", "verdict": "approved", "score": 95, "flags": []}]

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, return_value=discovery_result),
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock, return_value=reviews) as mock_reviews,
    ):
        result = await run_agent(
            "cleanup-before-review-2026",
            existing_data={},
            enabled_steps=["discovery", "review"],
            review_providers=["claude"],
        )

    assert mock_reviews.call_args.args[1]["candidates"][0]["social_media"] == {}
    assert result["pipeline_state"]["deterministic_cleanup"]["invalid_social_links_removed"] == 1


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
    assert result["pipeline_state"]["unresolved_review_flags"] == []


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
        result = await run_agent(
            "review-errors-2026",
            existing_data={},
            enabled_steps=["discovery", "review", "iteration"],
        )

    assert mock_iteration.await_count == 1
    assert mock_reviews.await_count == 2
    assert result["pipeline_state"]["unresolved_review_flags"] == ["candidates[0].summary"]


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
    assert issues["Tech & AI"]["stance"] == ""


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
        mock_loop.side_effect = [{"_tool_trace": {"required_final_tool_succeeded": True}}] + [{}] * 18

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

    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Pat Candidate", "Jordan Active"]


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


def test_authoritative_roster_adds_missing_candidates():
    race_json = {
        "id": "ar-senate-2026",
        "candidates": [{"name": "Tom Cotton", "party": "Republican", "issues": {}}],
    }

    _add_candidates_from_authoritative_roster(
        race_json,
        [
            {"name": "Tom Cotton", "party": "Republican", "incumbent": True},
            {"name": "Hallie Shoffner", "party": "Democratic", "incumbent": False},
            {"name": "Jeff Wadlin", "party": "Libertarian", "incumbent": False},
        ],
    )

    assert [candidate["name"] for candidate in race_json["candidates"]] == [
        "Tom Cotton",
        "Hallie Shoffner",
        "Jeff Wadlin",
    ]
    assert race_json["candidates"][1]["summary_sources"] == []
    assert race_json["candidates"][1]["issues"] == {}


@pytest.mark.asyncio
async def test_ballotpedia_sync_does_not_readd_primary_losers_after_primary():
    """Broad election pages are not proof that every listed primary candidate advanced."""
    from pipeline_client.agent import phases

    race_json = {
        "id": "co-house-08-2026",
        "contest_stage": "post_primary_general",
        "candidates": [
            {"name": "Gabe Evans", "party": "Republican", "summary": "Incumbent"},
            {"name": "Manny Rutinel", "party": "Democratic", "summary": "Nominee"},
        ],
    }
    broad_primary_roster = {
        "found": True,
        "candidates": [
            {"name": "Gabe Evans", "party": "Republican"},
            {"name": "Manny Rutinel", "party": "Democratic"},
            {"name": "Barbara Kirkmeyer", "party": "Republican"},
            {"name": "Primary Loser", "party": "Democratic"},
        ],
    }

    with patch.object(phases, "_ballotpedia_election_lookup", new=AsyncMock(return_value=broad_primary_roster)):
        await phases._sync_ballotpedia_roster(race_json, "co-house-08-2026")

    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Gabe Evans", "Manny Rutinel"]


@pytest.mark.asyncio
async def test_ballotpedia_sync_does_not_replace_researched_roster_with_blank_historical_candidates():
    """A scraped roster is advisory; official-source/model verification owns edits."""
    from pipeline_client.agent import phases

    race_json = {
        "id": "md-house-01-2026",
        "candidates": [
            {
                "name": "Andy Harris",
                "party": "Republican",
                "incumbent": True,
                "summary": "Harris is the sitting representative.",
            }
        ],
        "reviews": [{"reviewer": "test"}],
        "validation_grade": {"grade": "A", "passed": True},
    }
    stale_roster = {
        "found": True,
        "candidates": [
            {"name": "Historical Candidate One", "party": "Republican"},
            {"name": "Historical Candidate Two", "party": "Democratic"},
            {"name": "Historical Candidate Three", "party": "Republican"},
        ],
    }

    with patch.object(phases, "_ballotpedia_election_lookup", new=AsyncMock(return_value=stale_roster)):
        await phases._sync_ballotpedia_roster(race_json, "md-house-01-2026")

    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Andy Harris"]
    assert race_json["candidates"][0]["summary"] == "Harris is the sitting representative."
    assert race_json["reviews"] == [{"reviewer": "test"}]
    assert race_json["validation_grade"] == {"grade": "A", "passed": True}


def test_authoritative_roster_does_not_empty_race():
    race_json = {
        "id": "single-candidate-2026",
        "candidates": [{"name": "Existing Candidate", "party": "Independent"}],
    }

    _reconcile_candidates_with_authoritative_roster(
        race_json,
        [
            {"name": "Different Candidate", "party": "Democratic"},
            {"name": "Another Candidate", "party": "Republican"},
        ],
    )

    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Existing Candidate"]


def test_authoritative_roster_preserves_candidate_when_bp_returns_single_party():
    """Ballotpedia sometimes returns only the primary page for one party.

    When the profile has an incumbent of party A and BP returns only party B
    candidates (primary page), the incumbent must NOT be removed — their party
    simply isn't represented in that BP snapshot.
    """
    race_json = {
        "id": "wi-house-08-2026",
        "candidates": [
            {"name": "Tony Wied", "party": "Republican", "incumbent": True},
            {"name": "Rick Crosson", "party": "Democratic", "incumbent": False},
        ],
    }

    _reconcile_candidates_with_authoritative_roster(
        race_json,
        [
            {"name": "Rick Crosson", "party": "Democratic"},
            {"name": "Mark Scheffler", "party": "Democratic"},
            {"name": "Katrina deVille", "party": "Democratic"},
        ],
    )

    names = [c["name"] for c in race_json["candidates"]]
    assert "Tony Wied" in names, "Republican incumbent must not be removed when BP returns only Dem primary candidates"
    assert "Rick Crosson" in names


def test_authoritative_roster_still_removes_stale_primary_candidate_same_party():
    """Stale same-party primary losers should still be removed even with the new logic."""
    race_json = {
        "id": "ga-senate-2026",
        "candidates": [
            {"name": "Jon Ossoff", "party": "Democratic", "incumbent": True},
            {"name": "Primary Loser", "party": "Democratic", "incumbent": False},
            {"name": "Mike Collins", "party": "Republican", "incumbent": False},
        ],
    }

    _reconcile_candidates_with_authoritative_roster(
        race_json,
        [
            {"name": "Jon Ossoff", "party": "Democratic"},
            {"name": "Mike Collins", "party": "Republican"},
        ],
    )

    names = [c["name"] for c in race_json["candidates"]]
    assert "Jon Ossoff" in names
    assert "Mike Collins" in names
    assert "Primary Loser" not in names, "Same-party primary loser should be removed"


def test_sanitize_roster_caps_crowded_roster_to_eight_balanced():
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

    parties = [candidate["party"] for candidate in race_json["candidates"]]
    assert len(race_json["candidates"]) == 8
    assert parties.count("Democratic") == 4
    assert parties.count("Republican") == 4
    assert "candidate_limit_note" not in race_json


def test_sanitize_roster_removes_known_ineligible_from_race_identity():
    from pipeline_client.agent.phases import _remove_known_ineligible_candidates

    race_json = {
        "candidates": [
            {"name": "Jon Ossoff", "party": "Democratic", "incumbent": True},
            {"name": "Mike Collins", "party": "Republican"},
            {"name": "Raphael Warnock", "party": "Democratic"},  # off-cycle senator
            {"name": "Herschel Walker", "party": "Republican"},  # prior cycle
        ],
        "pipeline_state": {
            "race_identity": {
                "known_ineligible_or_not_running": ["Raphael Warnock", "Herschel Walker"],
            }
        },
    }
    _remove_known_ineligible_candidates(race_json)
    names = [c["name"] for c in race_json["candidates"]]
    assert names == ["Jon Ossoff", "Mike Collins"]


def test_cap_roster_keeps_incumbent_and_minor_party_when_room():
    from pipeline_client.agent.phases import _cap_roster

    race_json = {
        "candidates": [
            {"name": "Dem Incumbent", "party": "Democratic", "incumbent": True},
            *[{"name": f"Rep {i}", "party": "Republican"} for i in range(10)],
            {"name": "Indie One", "party": "Independent"},
        ],
    }
    _cap_roster(race_json)
    names = [c["name"] for c in race_json["candidates"]]
    assert len(names) == 8
    assert "Dem Incumbent" in names  # incumbent always survives the cap


def _capped(candidates, **race_fields):
    from pipeline_client.agent.phases import _cap_roster

    race_json = {"candidates": candidates, **race_fields}
    _cap_roster(race_json)
    return [c["name"] for c in race_json["candidates"]]


def _filler(prefix, party, count):
    return [{"name": f"{prefix}{i}", "party": party, "summary": "s", "roster_sources": [{"url": "u"}]} for i in range(count)]


def test_cap_roster_keeps_an_incumbent_who_belongs_to_neither_major_party():
    """The reserved slots are keyed on party and were filled before signal was
    consulted, so an independent incumbent — Vermont's and Maine's senators, a
    governor elected outside both parties — was dropped for a fourth Republican
    despite incumbency outweighing every other signal a hundred to one."""
    names = _capped(
        _filler("D", "Democratic", 4)
        + _filler("R", "Republican", 4)
        + [{"name": "Independent Incumbent", "party": "Independent", "incumbent": True, "summary": "s"}]
    )
    assert "Independent Incumbent" in names
    assert len(names) == 8


def test_cap_roster_ignores_party_balance_in_a_top_four_contest():
    """Alaska advances the top four regardless of party, so reserving seats for
    the two major parties describes a contest that is not being held. Its
    governor field — twelve Republicans, two Democrats, three independents —
    filled the cap with six Republicans and dropped every independent."""
    names = _capped(
        _filler("R", "Republican", 12)
        + _filler("D", "Democratic", 2)
        + [
            {
                "name": "Notable Independent",
                "party": "Independent",
                "summary": "s",
                "roster_sources": [{"url": "u"}],
                "image_url": "i",
            }
        ]
        + _filler("I", "Independent", 2),
        contest_stage="top_four_rcv",
    )
    assert "Notable Independent" in names, "a well-sourced independent must outrank a bare Republican"
    assert len(names) == 8


def test_cap_roster_ignores_party_balance_in_a_top_two_contest():
    names = _capped(
        _filler("R", "Republican", 8)
        + [
            {
                "name": "Notable Independent",
                "party": "Independent",
                "summary": "s",
                "roster_sources": [{"url": "u"}],
                "image_url": "i",
            }
        ],
        contest_stage="top_two",
    )
    assert "Notable Independent" in names


def test_cap_roster_still_balances_a_two_party_general():
    """The party reservation is right for a normal general and must be kept."""
    names = _capped(
        _filler("D", "Democratic", 5) + _filler("R", "Republican", 5),
        contest_stage="post_primary_general",
    )
    assert sum(1 for n in names if n.startswith("D")) == 4
    assert sum(1 for n in names if n.startswith("R")) == 4


def test_cap_roster_leaves_a_short_roster_alone():
    names = _capped(_filler("D", "Democratic", 2) + _filler("R", "Republican", 2), contest_stage="top_four_rcv")
    assert len(names) == 4


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
                "pollster": "Reliable Research",
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
                "pollster": "Public Policy Research",
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

    assert [poll["pollster"] for poll in race_json["polling"]] == ["Public Policy Research", "Valid Poll"]
    assert race_json["polling"][0]["matchups"] == []


def test_sanitize_polling_dedupes_sponsor_copy_and_clears_contradictory_note():
    matchup = [{"candidates": ["Alice Smith", "Bob Jones"], "percentages": [44, 45]}]
    race_json = {
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling_note": "Impact Research and DCCC both show Alice 44 and Bob 45.",
        "polling": [
            {
                "pollster": "Impact Research",
                "date": "2026-07-14",
                "sample_size": 400,
                "matchups": copy.deepcopy(matchup),
            },
            {
                "pollster": "Democratic Congressional Campaign Committee (DCCC)",
                "date": "2026-07-13",
                "sample_size": 400,
                "matchups": copy.deepcopy(matchup),
            },
        ],
    }

    _sanitize_polling(race_json)

    assert [poll["pollster"] for poll in race_json["polling"]] == ["Impact Research"]
    assert race_json["polling_note"] is None


def test_sanitize_polling_prefers_pollster_when_sponsor_copy_comes_first():
    matchup = [{"candidates": ["Alice Smith", "Bob Jones"], "percentages": [44, 45]}]
    race_json = {
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [
            {
                "pollster": "DCCC",
                "date": "2026-07-13",
                "sample_size": 400,
                "matchups": copy.deepcopy(matchup),
            },
            {
                "pollster": "Impact Research",
                "date": "2026-07-14",
                "sample_size": 400,
                "matchups": copy.deepcopy(matchup),
            },
        ],
    }

    _sanitize_polling(race_json)

    assert [poll["pollster"] for poll in race_json["polling"]] == ["Impact Research"]


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
        mock_loop.side_effect = [{"_tool_trace": {"required_final_tool_succeeded": True}}] + [{}] * 4
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
async def test_run_agent_continuation_skips_terminal_no_position_results():
    """A reasoned no-position verdict is complete even though it is a quality gap."""
    existing = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "party": "D",
                "issues": {
                    CANONICAL_ISSUES[0]: {
                        "issue": CANONICAL_ISSUES[0],
                        "stance": "No public position found after repeated research attempts.",
                        "confidence": "low",
                        "sources": [],
                        "research_audit": {"status": "completed", "search_calls": 2, "page_fetches": 0},
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

    assert mock_loop.call_count == len(CANONICAL_ISSUES) - 1
    assert f"issues:Alice:{CANONICAL_ISSUES[0]}" in result["pipeline_state"]["completed_units"]


@pytest.mark.asyncio
async def test_run_agent_continuation_retries_no_position_without_publishable_audit():
    existing = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "party": "D",
                "issues": {
                    CANONICAL_ISSUES[0]: {
                        "issue": CANONICAL_ISSUES[0],
                        "stance": "No public position found",
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
    assert not result["candidates"][0]["issues"][capped_issue]["stance"]
    assert f"issues:Alice:{capped_issue}" not in result["pipeline_state"]["completed_units"]
    assert result["pipeline_state"]["issue_research"][f"issues:Alice:{capped_issue}"]["status"] == "retry_limit"


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
                "sources": [{"url": f"https://example.com/{candidate}/{issue}"}],
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
                "sources": [{"url": f"https://example.com/{candidate}/{issue}"}],
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
                "sources": [{"url": f"https://example.com/{candidate}/{issue}"}],
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
