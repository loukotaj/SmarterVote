"""Retry-limit behaviour for issue units.

A unit that exhausts its retries used to leave the issue slot empty, which made
missing_issue_count non-zero and the whole race unpublishable over one issue —
observed on ne-house-02-2026, where 35 of 36 units landed and the race could not
be published.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipeline_client.agent.phases.context import PhaseContext
from pipeline_client.agent.phases.issues import run_issues_phase


def _race():
    return {
        "id": "ne-house-02-2026",
        "candidates": [{"name": "Brinker Harding", "issues": {}}],
        "pipeline_state": {
            "completed_units": [],
            "issue_attempts": {},
            "issue_research": {},
        },
    }


async def _run(race_json):
    await run_issues_phase(
        PhaseContext(
            race_json=race_json,
            race_id="ne-house-02-2026",
            model="test-model",
            small_model="test-model",
            on_log=None,
            log=lambda *_a, **_kw: None,
            max_iterations=1,
            step_enabled=lambda _s: True,
            track=lambda *_a, **_kw: None,
            run_budget=None,
            is_update=True,
            candidate_names=["Brinker Harding"],
            selected_name_set={"Brinker Harding"},
            last_updated="",
            max_candidates=None,
            target_no_info=False,
            resume_partial=True,
            continue_incomplete_work=False,
        )
    )


@pytest.mark.asyncio
async def test_exhausted_unit_with_real_research_records_documented_absence(monkeypatch):
    race_json = _race()
    unit = "issues:Brinker Harding:Civil Rights & Equality"
    race_json["pipeline_state"]["issue_attempts"][unit] = 99
    race_json["pipeline_state"]["issue_research"][unit] = {"search_calls": 2, "page_fetches": 1}

    await _run(race_json)

    stance = race_json["candidates"][0]["issues"].get("Civil Rights & Equality")
    assert stance is not None, "an exhausted unit that did research must not leave the slot empty"
    assert stance["stance"] == "No public position found"
    assert stance["research_audit"]["status"] == "completed"
    assert stance["research_audit"]["search_calls"] == 2


@pytest.mark.asyncio
async def test_exhausted_unit_without_research_stays_open(monkeypatch):
    """Never assert an absence nothing actually looked for."""
    race_json = _race()
    unit = "issues:Brinker Harding:Civil Rights & Equality"
    race_json["pipeline_state"]["issue_attempts"][unit] = 99
    race_json["pipeline_state"]["issue_research"][unit] = {"search_calls": 0, "page_fetches": 0}

    await _run(race_json)

    assert "Civil Rights & Equality" not in race_json["candidates"][0]["issues"]
    failures = race_json["pipeline_state"].get("step_failures") or []
    assert any("retry limit" in str(f.get("detail", "")) for f in failures)


@pytest.mark.asyncio
async def test_source_hint_timeout_falls_back_without_handing_off(monkeypatch):
    """A slow campaign-site crawl is advisory and must not restart the whole run."""
    from pipeline_client.agent.phases import issues as issues_phase

    race_json = _race()
    race_json["candidates"][0]["website"] = "https://example.test/candidate"

    async def time_out_advisory(awaitable, **_kwargs):
        awaitable.close()
        return None

    advisory = AsyncMock(side_effect=time_out_advisory)

    async def research(candidate_name, issue_name, _candidate, **kwargs):
        assert candidate_name == "Brinker Harding"
        assert kwargs["candidate_website"] == "https://example.test/candidate"
        assert kwargs["candidate_issue_urls"] == []
        return (
            {
                "issue": issue_name,
                "stance": f"Position on {issue_name}",
                "confidence": "medium",
                "sources": [{"url": "https://example.test/source", "type": "website"}],
            },
            {"search_calls": 1, "page_fetches": 1},
        )

    monkeypatch.setattr(issues_phase, "_await_advisory_with_run_budget", advisory)
    monkeypatch.setattr(issues_phase, "_research_issue_unit", research)

    await _run(race_json)

    assert advisory.await_count == 1
    assert len(race_json["candidates"][0]["issues"]) == 12
    assert race_json["pipeline_state"]["remaining_candidates"] == []
