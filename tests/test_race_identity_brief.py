"""Tests for Phase 1 of docs/pipeline-result-quality-plan.md — the race identity
brief and its propagation into every downstream research/review phase.

Covers:
- ``phase_state.race_identity_context`` rendering (locked brief, fallback to
  top-level race fields, and the "not yet locked" notice).
- The locked identity reaching the issue-research, finance, polling, forecast,
  iteration, and review prompts so a same-state wrong-office candidate cannot
  drift into an unrelated race partway through a run.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from pipeline_client.agent.phase_state import race_identity_context

# ---------------------------------------------------------------------------
# race_identity_context() rendering
# ---------------------------------------------------------------------------


def test_race_identity_context_renders_locked_brief():
    """A fully-populated pipeline_state.race_identity renders every field."""
    race_json = {
        "pipeline_state": {
            "race_identity": {
                "office": "Governor",
                "state": "Alabama",
                "district": None,
                "contest_stage": "post_primary_general",
                "election_date": "2026-11-03",
                "primary_status": "Republican and Democratic nominees certified.",
                "official_roster_source_url": "https://sos.alabama.gov/2026-candidates",
                "known_incumbent": "Kay Ivey",
                "known_ineligible_or_not_running": ["Kay Ivey"],
            }
        }
    }

    result = race_identity_context(race_json)

    assert "Locked race identity" in result
    assert "Office: Governor" in result
    assert "State: Alabama" in result
    assert "Contest stage: post_primary_general" in result
    assert "Election date: 2026-11-03" in result
    assert "Primary status: Republican and Democratic nominees certified." in result
    assert "Known incumbent: Kay Ivey" in result
    assert "known_ineligible_or_not_running" not in result  # rendered as prose, not the raw key
    assert "Kay Ivey" in result
    assert "https://sos.alabama.gov/2026-candidates" in result
    # District is None and must not appear as the literal string "None".
    assert "District: None" not in result


def test_race_identity_context_wrong_office_names_are_surfaced():
    """A Senate candidate recorded as ineligible for a Governor race is named explicitly.

    Regression guard for the "wrong-office contamination" symptom in the
    quality plan: same-state candidates from a different office must be
    listed by name so every downstream phase can avoid re-introducing them.
    """
    race_json = {
        "pipeline_state": {
            "race_identity": {
                "office": "Governor",
                "state": "Georgia",
                "contest_stage": "post_primary_general",
                "known_ineligible_or_not_running": ["Jon Ossoff", "Raphael Warnock"],
            }
        }
    }

    result = race_identity_context(race_json)

    assert "Office: Governor" in result
    assert "State: Georgia" in result
    assert "Jon Ossoff" in result
    assert "Raphael Warnock" in result
    assert "never re-add or attribute facts to these" in result


def test_race_identity_context_falls_back_to_top_level_race_fields():
    """Drafts created before this feature existed still get useful context."""
    race_json = {"office": "U.S. House", "state": "Michigan", "district": "8th Congressional District"}

    result = race_identity_context(race_json)

    assert "Locked race identity" in result
    assert "Office: U.S. House" in result
    assert "State: Michigan" in result
    assert "District: 8th Congressional District" in result


def test_race_identity_context_reports_not_locked_when_nothing_recorded():
    result = race_identity_context({})

    assert "not yet locked" in result
    assert "different office, state, district, or election cycle" in result


# ---------------------------------------------------------------------------
# Issue research
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_issue_unit_includes_locked_identity_in_prompt():
    from pipeline_client.agent.phases import _research_issue_unit

    identity_text = "Locked race identity (do not drift from this exact contest):\n- Office: Governor\n- State: Alabama"

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        await _research_issue_unit(
            "Alice Example",
            "Healthcare",
            {"name": "Alice Example", "issues": {}},
            race_id="al-governor-2026",
            model="test-model",
            on_log=None,
            max_iterations=4,
            is_update=False,
            last_updated="",
            candidate_website="",
            candidate_issue_urls=[],
            run_budget=None,
            race_identity_context=identity_text,
        )

    assert mock_loop.await_count == 1
    user_prompt = mock_loop.call_args.args[1]
    assert identity_text in user_prompt


@pytest.mark.asyncio
async def test_research_issue_unit_defaults_to_not_locked_notice():
    """Callers that omit race_identity_context still get an explicit notice, not a blank gap."""
    from pipeline_client.agent.phases import _research_issue_unit

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        await _research_issue_unit(
            "Alice Example",
            "Healthcare",
            {"name": "Alice Example", "issues": {}},
            race_id="al-governor-2026",
            model="test-model",
            on_log=None,
            max_iterations=4,
            is_update=False,
            last_updated="",
            candidate_website="",
            candidate_issue_urls=[],
            run_budget=None,
        )

    user_prompt = mock_loop.call_args.args[1]
    assert "not yet locked" in user_prompt


# ---------------------------------------------------------------------------
# Finance, polling, forecast (shared phase fan-out)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finance_polling_forecast_prompts_include_locked_race_identity():
    from pipeline_client.agent.agent import run_agent

    existing = {
        "id": "al-governor-2026",
        "office": "Governor",
        "state": "Alabama",
        "election_date": "2026-11-03",
        "updated_utc": "2026-06-01T00:00:00Z",
        "candidates": [{"name": "Alice Example", "party": "Democratic"}],
        "polling": [],
        "pipeline_state": {
            "race_identity": {
                "office": "Governor",
                "state": "Alabama",
                "contest_stage": "post_primary_general",
                "known_incumbent": "Kay Ivey",
                "known_ineligible_or_not_running": ["Kay Ivey"],
            }
        },
    }

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.phases._sync_ballotpedia_roster", new_callable=AsyncMock),
        patch("pipeline_client.agent.phases.fetch_kalshi_market_signals", new_callable=AsyncMock, return_value=[]),
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        await run_agent(
            "al-governor-2026",
            existing_data=existing,
            enabled_steps=["finance", "polling", "forecast"],
        )

    prompts_by_phase = {call.kwargs.get("phase_name"): call.args[1] for call in mock_loop.call_args_list}

    for phase_name in ("update-finance-voting", "update-polling", "update-forecast"):
        assert phase_name in prompts_by_phase, sorted(prompts_by_phase)
        prompt = prompts_by_phase[phase_name]
        assert "Office: Governor" in prompt
        assert "State: Alabama" in prompt
        assert "Kay Ivey" in prompt


# ---------------------------------------------------------------------------
# Iteration (per-candidate and race-level metadata pass)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iteration_pass_prompts_include_locked_race_identity():
    from pipeline_client.agent.phases import _run_iteration_pass

    race_json = {
        "id": "al-governor-2026",
        "candidates": [{"name": "Alice Example"}],
        "pipeline_state": {
            "race_identity": {
                "office": "Governor",
                "state": "Alabama",
                "contest_stage": "post_primary_general",
            }
        },
    }

    with (
        patch("pipeline_client.agent.phases._candidate_source_hints", new_callable=AsyncMock, return_value=("", [])),
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock, return_value={}) as mock_loop,
    ):
        await _run_iteration_pass(
            "al-governor-2026",
            race_json,
            [{"model": "claude", "flags": [{"field": "summary", "severity": "warning"}]}],
            model="test-model",
        )

    prompts_by_phase = {call.kwargs.get("phase_name"): call.args[1] for call in mock_loop.call_args_list}
    assert "iterate-Alice Example" in prompts_by_phase
    assert "iterate-meta" in prompts_by_phase
    for phase_name in ("iterate-Alice Example", "iterate-meta"):
        assert "Office: Governor" in prompts_by_phase[phase_name]
        assert "State: Alabama" in prompts_by_phase[phase_name]


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_reviews_includes_locked_race_identity_for_roster_audit(monkeypatch):
    """Reviewers audit the roster against the SAME locked identity discovery recorded.

    ``pipeline_state`` is stripped from the semantic review packet (it is
    operational metadata, not race content), so without this the reviewer only
    has the race title/description to infer the exact office/state/district —
    this asserts the locked brief reaches the reviewer explicitly instead.
    """
    from pipeline_client.agent.review import run_reviews

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")

    race_json = {
        "schema_version": "0.3",
        "id": "ga-governor-2026",
        "election_date": "2026-11-03",
        "updated_utc": "2026-06-14T00:00:00Z",
        "title": "2026 Georgia Governor Election",
        "description": "Voters will elect a governor in the November 2026 general election.",
        "candidates": [{"name": "Alice Example"}],
        "pipeline_state": {
            "race_identity": {
                "office": "Governor",
                "state": "Georgia",
                "contest_stage": "post_primary_general",
                "known_ineligible_or_not_running": ["Jon Ossoff"],
            }
        },
    }

    received = []

    async def capture_review(_race_id, profile_json, *, provider, change_manifest, **kwargs):
        received.append(kwargs.get("race_identity_context_text", ""))
        return {"model": provider, "verdict": "approved", "flags": [], "summary": ""}

    with (
        patch("pipeline_client.agent.review._run_single_review", side_effect=capture_review),
        patch("pipeline_client.agent.review.check_profile_links", new_callable=AsyncMock, return_value=None),
    ):
        await run_reviews("ga-governor-2026", race_json)

    assert received
    for identity_text in received:
        assert "Office: Governor" in identity_text
        assert "State: Georgia" in identity_text
        assert "Jon Ossoff" in identity_text


@pytest.mark.asyncio
async def test_run_single_review_formats_locked_identity_into_prompt():
    from pipeline_client.agent.review import _run_single_review

    review_response = json.dumps({"verdict": "approved", "summary": "Looks good.", "flags": []})
    identity_text = "Locked race identity (do not drift from this exact contest):\n- Office: Governor\n- State: Georgia"

    with patch("pipeline_client.agent.review._call_review_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = review_response
        result = await _run_single_review(
            "ga-governor-2026",
            '{"id": "ga-governor-2026"}',
            provider="claude",
            race_identity_context_text=identity_text,
        )

    assert result is not None
    prompt_used = mock_call.call_args.args[1]
    assert identity_text in prompt_used
