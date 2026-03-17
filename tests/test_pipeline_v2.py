"""Tests for the pipeline v2 agent module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline_v2.agent import _extract_json, run_agent
from pipeline_v2.prompts import CANONICAL_ISSUES, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_canonical_issues_count():
    """All 12 canonical issues are defined."""
    assert len(CANONICAL_ISSUES) == 12


def test_system_prompt_contains_all_issues():
    """System prompt includes every canonical issue."""
    for issue in CANONICAL_ISSUES:
        assert issue in SYSTEM_PROMPT, f"Missing issue in system prompt: {issue}"


def test_user_prompt_template_formats():
    """User prompt template accepts race_id."""
    result = USER_PROMPT_TEMPLATE.format(race_id="mo-senate-2024")
    assert "mo-senate-2024" in result


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
# Agent integration test (mocked OpenAI + Serper)
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
async def test_run_agent_produces_race_json():
    """Agent loop returns valid race JSON when model gives final answer."""

    # Mock OpenAI response: model returns JSON directly (no tool calls)
    mock_openai_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(FAKE_RACE_JSON),
                }
            }
        ]
    }

    with patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_openai_response

        result = await run_agent("mo-senate-2024", cheap_mode=True)

    assert result["id"] == "mo-senate-2024"
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["name"] == "Jane Doe"
    assert "Healthcare" in result["candidates"][0]["issues"]


@pytest.mark.asyncio
async def test_run_agent_handles_tool_calls():
    """Agent executes web_search tool calls and then returns final answer."""

    # First call: model requests a web search
    tool_call_response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps(
                                    {"query": "Missouri Senate 2024 candidates"}
                                ),
                            },
                        }
                    ],
                    "content": None,
                }
            }
        ]
    }

    # Second call: model returns final JSON
    final_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(FAKE_RACE_JSON),
                }
            }
        ]
    }

    with (
        patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock_call,
        patch("pipeline_v2.agent._serper_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_call.side_effect = [tool_call_response, final_response]
        mock_search.return_value = [
            {
                "title": "Missouri Senate Race",
                "snippet": "Candidates competing...",
                "url": "https://example.com",
            }
        ]

        result = await run_agent("mo-senate-2024", cheap_mode=True)

    assert result["id"] == "mo-senate-2024"
    assert mock_search.call_count == 1
    assert mock_call.call_count == 2


@pytest.mark.asyncio
async def test_run_agent_retries_on_bad_json():
    """Agent asks model to fix output when JSON is invalid."""

    bad_response = {
        "choices": [
            {
                "message": {
                    "content": "Here is the result: not valid json",
                }
            }
        ]
    }

    good_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(FAKE_RACE_JSON),
                }
            }
        ]
    }

    with patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_response, good_response]

        result = await run_agent("mo-senate-2024", cheap_mode=True)

    assert result["id"] == "mo-senate-2024"
    # First call produced bad JSON, second call fixed it
    assert mock_call.call_count == 2


@pytest.mark.asyncio
async def test_run_agent_sets_defaults():
    """Agent sets default fields on the output JSON."""

    minimal_json = {"candidates": []}
    response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(minimal_json),
                }
            }
        ]
    }

    with patch("pipeline_v2.agent._call_openai", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = response

        result = await run_agent("test-race-2024", cheap_mode=True)

    assert result["id"] == "test-race-2024"
    assert "updated_utc" in result
    assert result["generator"] == ["pipeline-v2-agent"]
