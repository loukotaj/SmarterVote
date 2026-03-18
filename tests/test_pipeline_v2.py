"""Tests for the pipeline v2 agent module."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from pipeline_v2.agent import _extract_json, run_agent, _agent_loop
from pipeline_v2.prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    ISSUE_GROUPS,
    ISSUE_RESEARCH_SYSTEM,
    REFINE_SYSTEM,
    UPDATE_SYSTEM,
    UPDATE_USER,
)


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_canonical_issues_count():
    """All 12 canonical issues are defined."""
    assert len(CANONICAL_ISSUES) == 12


def test_all_issues_in_groups():
    """All canonical issues appear in at least one issue group."""
    grouped = {issue for group in ISSUE_GROUPS for issue in group}
    for issue in CANONICAL_ISSUES:
        assert issue in grouped, f"Issue {issue!r} not in any group"


def test_issue_groups_cover_all():
    """Issue groups have 6 pairs covering 12 issues."""
    assert len(ISSUE_GROUPS) == 6
    total = sum(len(g) for g in ISSUE_GROUPS)
    assert total == 12


def test_discovery_user_formats():
    """Discovery user prompt accepts race_id."""
    result = DISCOVERY_USER.format(race_id="mo-senate-2024")
    assert "mo-senate-2024" in result


def test_update_user_formats():
    """Update user prompt accepts race_id, existing_json, and last_updated."""
    result = UPDATE_USER.format(
        race_id="mo-senate-2024",
        existing_json='{"id": "test"}',
        last_updated="2024-01-01T00:00:00Z",
    )
    assert "mo-senate-2024" in result
    assert "2024-01-01" in result


def test_prompts_contain_rules():
    """All system prompts include shared rules."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_RESEARCH_SYSTEM, REFINE_SYSTEM, UPDATE_SYSTEM]:
        assert "nonpartisan" in prompt.lower()
        assert "web_search" in prompt


# ---------------------------------------------------------------------------
# JSON extraction tests
# ---------------------------------------------------------------------------


def test_extract_json_plain():
    """Plain JSON is parsed correctly."""
    data = _extract_json('{"id": "test", "candidates": []}')
    assert data == {"id": "test", "candidates": []}


def test_extract_json_fenced():
    """JSON wrapped in markdown fences is extracted."""
    fenced = '```json\n{"id": "test"}\n```'
    data = _extract_json(fenced)
    assert data == {"id": "test"}


def test_extract_json_fenced_no_lang():
    """JSON wrapped in plain fences (no language) is extracted."""
    fenced = '```\n{"id": "test"}\n```'
    data = _extract_json(fenced)
    assert data == {"id": "test"}


def test_extract_json_invalid():
    """Invalid JSON raises an error."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


# ---------------------------------------------------------------------------
# Agent loop tests
# ---------------------------------------------------------------------------

FAKE_RACE_JSON = {
    "id": "mo-senate-2024",
    "title": "Missouri U.S. Senate 2024",
    "office": "U.S. Senate",
    "jurisdiction": "Missouri",
    "election_date": "2024-11-05",
    "candidates": [
        {
            "name": "Jane Doe",
            "party": "Democratic",
            "incumbent": False,
            "summary": "Runs on healthcare reform.",
            "website": "https://janedoe.com",
            "social_media": {},
            "top_donors": [],
            "issues": {
                "Healthcare": {
                    "stance": "Supports universal coverage.",
                    "confidence": "high",
                    "sources": [
                        {
                            "url": "https://example.com/article",
                            "type": "news",
                            "title": "Jane Doe on healthcare",
                        }
                    ],
                }
            },
        }
    ],
    "updated_utc": "2024-01-01T00:00:00Z",
    "generator": ["pipeline-v2-agent"],
}


@pytest.mark.asyncio
async def test_agent_loop_produces_json():
    """_agent_loop returns parsed JSON when model gives a direct answer."""
    response = {
        "choices": [{"message": {"content": json.dumps({"result": "ok"})}}]
    }
    with patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.return_value = response
        result = await _agent_loop(
            "system", "user", model="gpt-4o-mini", phase_name="test"
        )
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_agent_loop_handles_tool_calls():
    """_agent_loop executes tool calls then returns final JSON."""
    tool_response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": "test"}),
                            },
                        }
                    ],
                    "content": None,
                }
            }
        ]
    }
    final_response = {
        "choices": [{"message": {"content": json.dumps({"done": True})}}]
    }

    with (
        patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock_call,
        patch("pipeline_v2.agent._serper_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_search.return_value = [{"title": "Test", "snippet": "...", "url": "https://test.com"}]

        result = await _agent_loop(
            "system", "user", model="gpt-4o-mini", phase_name="test"
        )

    assert result == {"done": True}
    assert mock_search.call_count == 1


@pytest.mark.asyncio
async def test_agent_loop_retries_bad_json():
    """_agent_loop asks model to fix output when JSON is invalid."""
    bad = {"choices": [{"message": {"content": "not json"}}]}
    good = {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}

    with patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.side_effect = [bad, good]
        result = await _agent_loop(
            "system", "user", model="gpt-4o-mini", phase_name="test"
        )

    assert result == {"ok": True}
    assert mock.call_count == 2


# ---------------------------------------------------------------------------
# Full agent tests (multi-phase)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_fresh():
    """run_agent with no existing data runs discovery → issues → refine."""
    discovery_result = {
        "id": "test-2024",
        "candidates": [{"name": "Alice", "issues": {}}],
    }
    issue_result = {
        "Alice": {
            "Healthcare": {
                "stance": "Supports ACA.",
                "confidence": "high",
                "sources": [],
            }
        }
    }
    refined_result = {
        "id": "test-2024",
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Healthcare": {"stance": "Expanded ACA.", "confidence": "high", "sources": []},
                },
            }
        ],
    }

    with (
        patch("pipeline_v2.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_v2.agent._load_existing", return_value=None),
    ):
        # discovery, 6 issue groups, refine = 8 total calls
        mock_loop.side_effect = [
            discovery_result,  # discovery
            issue_result,  # issue group 1
            issue_result,  # issue group 2
            issue_result,  # issue group 3
            issue_result,  # issue group 4
            issue_result,  # issue group 5
            issue_result,  # issue group 6
            refined_result,  # refine
        ]

        result = await run_agent("test-2024", cheap_mode=True)

    assert result["id"] == "test-2024"
    assert "updated_utc" in result
    assert result["generator"] == ["pipeline-v2-agent"]
    # discovery + 6 issue groups + refine = 8
    assert mock_loop.call_count == 8


@pytest.mark.asyncio
async def test_run_agent_update_mode():
    """run_agent with existing data runs in update mode."""
    existing = {"id": "test-2024", "candidates": [], "updated_utc": "2024-01-01"}
    updated = {"id": "test-2024", "candidates": [{"name": "Bob", "issues": {}}]}

    with (
        patch("pipeline_v2.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_v2.agent._load_existing", return_value=existing),
    ):
        mock_loop.return_value = updated
        result = await run_agent("test-2024", cheap_mode=True)

    assert result["id"] == "test-2024"
    # Only 1 call in update mode
    assert mock_loop.call_count == 1


@pytest.mark.asyncio
async def test_run_agent_normalizes_output():
    """run_agent sets defaults even when agent returns minimal JSON."""
    minimal = {"candidates": []}

    with (
        patch("pipeline_v2.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_v2.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = minimal
        result = await run_agent("race-2024", cheap_mode=True, existing_data={})

    assert result["id"] == "race-2024"
    assert "updated_utc" in result
    assert result["generator"] == ["pipeline-v2-agent"]
