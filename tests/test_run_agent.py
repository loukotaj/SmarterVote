"""Tests for run_agent orchestration and _load_existing helper."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pipeline_client.agent.agent import _load_existing, _normalize_schema_fields, _sanitize_polling, run_agent
from pipeline_client.agent.phases import _reconcile_candidates_with_authoritative_roster, _sanitize_roster
from pipeline_client.agent.prompts import CANONICAL_ISSUES
from pipeline_client.backend.handlers.agent import HandoffTriggered


@pytest.fixture(autouse=True)
def no_review_provider_keys(monkeypatch):
    """Unit tests mock agent phases; never call real review providers."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)


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
    assert result["generator"] == ["gpt-5.4-mini", "gpt-5-nano"]
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
async def test_run_agent_caps_fresh_roster_at_eight_candidates():
    """Oversized primary-style rosters are capped before downstream phase fan-out."""
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

    assert [candidate["name"] for candidate in result["candidates"]] == [
        "Candidate 1",
        "Candidate 2",
        "Candidate 3",
        "Candidate 4",
        "Candidate 6",
        "Candidate 7",
        "Candidate 8",
        "Candidate 9",
    ]
    assert "capped at 8" in result["candidate_limit_note"]


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
    # Falls back to fresh: 1 discovery + 1 image + 12 issues + 1 finance + 1 refinement = 16
    assert mock_loop.call_count == 16


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
    assert result["generator"] == ["gpt-5.4-mini", "gpt-5-nano"]


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
    """run_agent selects gpt-5.4-mini in cheap mode and gpt-5.4 otherwise."""
    discovery_result = {"id": "m-2024", "candidates": []}

    for cheap_mode, expected_model in [(True, "gpt-5.4-mini"), (False, "gpt-5.4")]:
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
    assert issues["Tech & AI"]["stance"] == "No public position found"


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
async def test_run_agent_review_skips_without_keys():
    """run_agent review step skips providers without API keys."""
    discovery_result = {"id": "review-2024", "candidates": []}

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("GEMINI_API_KEY", None)
    env.pop("XAI_API_KEY", None)

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch.dict(os.environ, env, clear=True),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("review-2024", cheap_mode=True, existing_data={})

    # No reviews because no API keys are set
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
    # roster sync + meta + images + 12 issues + finance + refine + meta refine = 18
    assert mock_loop.call_count == 18


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
async def test_issue_checkpoint_progress_includes_partial_race_json():
    """Issue checkpoints send the mutated RaceJSON to the handler for handoff storage."""
    existing = {
        "id": "test-2024",
        "candidates": [{"name": "Alice", "party": "D", "issues": {}}],
        "updated_utc": "2024-01-01T00:00:00Z",
    }
    progress_payloads = []

    def _progress(step: str, **kwargs):
        if step == "issues" and "race_json" in kwargs:
            progress_payloads.append(kwargs["race_json"])

    with patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = {}

        await run_agent(
            "test-2024",
            cheap_mode=True,
            existing_data=existing,
            enabled_steps=["issues"],
            step_tracker={"progress": _progress},
        )

    assert len(progress_payloads) == len(CANONICAL_ISSUES)
    assert progress_payloads[-1]["id"] == "test-2024"
