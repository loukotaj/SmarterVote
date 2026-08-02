"""Retry-limit behaviour for issue units.

A unit that exhausts its retries used to leave the issue slot empty, which made
missing_issue_count non-zero and the whole race unpublishable over one issue —
observed on ne-house-02-2026, where 35 of 36 units landed and the race could not
be published.
"""

from __future__ import annotations

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
