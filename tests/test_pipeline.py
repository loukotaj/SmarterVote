"""Tests for the pipeline v2 agent module.

Covers:
- Prompt templates and formatting
- Issue group coverage
- JSON extraction from LLM output
- Agent loop (direct answers, tool calls, retries)
- Multi-phase fresh run orchestration
- Update/rerun mode
- Output normalization and defaults
- Search caching integration
- Serper search function
- Handler integration
- Load existing data helper
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline_client.agent.agent import SEARCH_TOOL, _agent_loop, _extract_json, _load_existing, _serper_search, run_agent
from pipeline_client.agent.prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    ISSUE_GROUPS,
    ISSUE_RESEARCH_SYSTEM,
    ISSUE_RESEARCH_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    UPDATE_SYSTEM,
    UPDATE_USER,
)

# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_canonical_issues_count():
    """All 12 canonical issues are defined."""
    assert len(CANONICAL_ISSUES) == 12


def test_canonical_issues_no_duplicates():
    """No duplicate canonical issues."""
    assert len(CANONICAL_ISSUES) == len(set(CANONICAL_ISSUES))


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


def test_issue_groups_no_overlaps():
    """No issue appears in more than one group."""
    seen = set()
    for group in ISSUE_GROUPS:
        for issue in group:
            assert issue not in seen, f"Issue {issue!r} in multiple groups"
            seen.add(issue)


def test_discovery_user_formats():
    """Discovery user prompt accepts race_id."""
    result = DISCOVERY_USER.format(race_id="mo-senate-2024")
    assert "mo-senate-2024" in result


def test_issue_research_user_formats():
    """Issue research user prompt accepts all required variables."""
    result = ISSUE_RESEARCH_USER.format(
        race_id="mo-senate-2024",
        candidate_names="Alice, Bob",
        issues_list="  - Healthcare\n  - Education",
    )
    assert "mo-senate-2024" in result
    assert "Alice, Bob" in result
    assert "Healthcare" in result


def test_refine_user_formats():
    """Refine user prompt accepts race_id, draft_json, all_issues."""
    result = REFINE_USER.format(
        race_id="mo-senate-2024",
        draft_json='{"id": "test"}',
        all_issues="Healthcare, Economy",
    )
    assert "mo-senate-2024" in result
    assert '{"id": "test"}' in result
    assert "Healthcare, Economy" in result


def test_update_user_formats():
    """Update user prompt accepts race_id, existing_json, and last_updated."""
    result = UPDATE_USER.format(
        race_id="mo-senate-2024",
        existing_json='{"id": "test"}',
        last_updated="2024-01-01T00:00:00Z",
    )
    assert "mo-senate-2024" in result
    assert "2024-01-01" in result


def test_discovery_prompt_mentions_donor_sources():
    """Discovery prompt tells the model to include donor sources."""
    result = DISCOVERY_USER.format(race_id="mo-senate-2024")
    assert "top_donors" in result
    assert '"source": {"url": "<url>"' in result


def test_refine_prompt_mentions_donor_sources():
    """Refine prompt requires source objects on donor entries."""
    result = REFINE_USER.format(
        race_id="mo-senate-2024",
        draft_json='{"id": "test"}',
        all_issues="Healthcare, Economy",
    )
    assert "source object on every donor entry" in result


def test_update_prompt_mentions_donor_sources():
    """Update prompt requires donor source objects during reruns."""
    result = UPDATE_USER.format(
        race_id="mo-senate-2024",
        existing_json='{"id": "test"}',
        last_updated="2024-01-01T00:00:00Z",
    )
    assert "top_donors" in result
    assert "source object on every donor item" in result


def test_prompts_contain_rules():
    """All system prompts include shared rules."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_RESEARCH_SYSTEM, REFINE_SYSTEM, UPDATE_SYSTEM]:
        assert "nonpartisan" in prompt.lower()
        assert "web_search" in prompt


def test_prompts_mention_confidence_levels():
    """All system prompts describe the confidence levels."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_RESEARCH_SYSTEM, REFINE_SYSTEM, UPDATE_SYSTEM]:
        assert "high" in prompt.lower()
        assert "medium" in prompt.lower()
        assert "low" in prompt.lower()


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


def test_extract_json_with_whitespace():
    """JSON with leading/trailing whitespace is parsed."""
    data = _extract_json('  \n {"id": "test"} \n  ')
    assert data == {"id": "test"}


def test_extract_json_nested():
    """Nested JSON objects are parsed correctly."""
    nested = json.dumps({"a": {"b": {"c": [1, 2, 3]}}})
    data = _extract_json(nested)
    assert data["a"]["b"]["c"] == [1, 2, 3]


def test_extract_json_invalid():
    """Invalid JSON raises an error."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


# ---------------------------------------------------------------------------
# Search tool definition tests
# ---------------------------------------------------------------------------


def test_search_tool_schema():
    """SEARCH_TOOL has the expected structure for OpenAI function calling."""
    assert SEARCH_TOOL["type"] == "function"
    assert SEARCH_TOOL["function"]["name"] == "web_search"
    assert "query" in SEARCH_TOOL["function"]["parameters"]["properties"]
    assert "query" in SEARCH_TOOL["function"]["parameters"]["required"]


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
    "generator": ["pipeline-agent"],
}


@pytest.mark.asyncio
async def test_agent_loop_produces_json():
    """_agent_loop returns parsed JSON when model gives a direct answer."""
    response = {"choices": [{"message": {"content": json.dumps({"result": "ok"})}}]}
    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.return_value = response
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")
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
    final_response = {"choices": [{"message": {"content": json.dumps({"done": True})}}]}

    with (
        patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.agent._serper_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_search.return_value = [{"title": "Test", "snippet": "...", "url": "https://test.com"}]

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"done": True}
    assert mock_search.call_count == 1


@pytest.mark.asyncio
async def test_agent_loop_handles_multiple_tool_calls():
    """_agent_loop handles multiple tool calls in a single response."""
    tool_response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": "query 1"}),
                            },
                        },
                        {
                            "id": "call_2",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": "query 2"}),
                            },
                        },
                    ],
                    "content": None,
                }
            }
        ]
    }
    final_response = {"choices": [{"message": {"content": json.dumps({"done": True})}}]}

    with (
        patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.agent._serper_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_search.return_value = [{"title": "R", "snippet": "...", "url": "https://r.com"}]

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"done": True}
    assert mock_search.call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_retries_bad_json():
    """_agent_loop asks model to fix output when JSON is invalid."""
    bad = {"choices": [{"message": {"content": "not json"}}]}
    good = {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}

    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.side_effect = [bad, good]
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"ok": True}
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_raises_on_max_iterations():
    """_agent_loop raises RuntimeError when max iterations reached."""
    bad = {"choices": [{"message": {"content": "still not json"}}]}

    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.return_value = bad
        with pytest.raises(RuntimeError, match="did not produce output"):
            await _agent_loop(
                "system",
                "user",
                model="gpt-5.4-mini",
                phase_name="test",
                max_iterations=2,
            )


@pytest.mark.asyncio
async def test_agent_loop_passes_race_id_to_search():
    """_agent_loop passes race_id to _serper_search for cache scoping."""
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
    final_response = {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}

    with (
        patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.agent._serper_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_search.return_value = []

        await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test",
            race_id="my-race-2024",
        )

    mock_search.assert_called_once_with("test", race_id="my-race-2024")


# ---------------------------------------------------------------------------
# Serper search tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serper_search_no_api_key():
    """_serper_search returns error when SERPER_API_KEY is not set."""
    env = os.environ.copy()
    env.pop("SERPER_API_KEY", None)
    with (
        patch.dict(os.environ, env, clear=True),
        patch("pipeline_client.agent.agent._get_search_cache", return_value=None),
    ):
        results = await _serper_search("test query")
    assert len(results) == 1
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_serper_search_uses_cache():
    """_serper_search returns cached results when available."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = {"results": [{"title": "Cached", "snippet": "...", "url": "https://cached.com"}]}

    with patch("pipeline_client.agent.agent._get_search_cache", return_value=mock_cache):
        results = await _serper_search("test query", race_id="my-race")

    assert results == [{"title": "Cached", "snippet": "...", "url": "https://cached.com"}]
    mock_cache.get.assert_called_once_with("test query", "my-race")


# ---------------------------------------------------------------------------
# Load existing data tests
# ---------------------------------------------------------------------------


def test_load_existing_returns_none_for_missing():
    """_load_existing returns None when no published file exists."""
    result = _load_existing("nonexistent-race-9999")
    assert result is None


def test_load_existing_reads_file():
    """_load_existing reads and parses a published JSON file."""
    test_data = {"id": "test-race", "candidates": []}
    # Use a clearly-test-only filename to avoid collisions
    published_dir = Path(__file__).resolve().parents[1] / "data" / "published"
    published_dir.mkdir(parents=True, exist_ok=True)
    test_file = published_dir / "__test_tmp_load_existing__.json"

    try:
        with test_file.open("w") as f:
            json.dump(test_data, f)
        result = _load_existing("__test_tmp_load_existing__")
        assert result is not None
        assert result["id"] == "test-race"
    finally:
        test_file.unlink(missing_ok=True)


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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        # discovery, image resolution (1 candidate), 6 issue groups, refine = 9 total calls
        mock_loop.side_effect = [
            discovery_result,  # discovery
            {"image_url": None},  # image resolution for Alice
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
    assert result["generator"] == ["gpt-5.4-mini"]
    # discovery + image resolution + 6 issue groups + refine = 9
    assert mock_loop.call_count == 9


@pytest.mark.asyncio
async def test_run_agent_fresh_no_candidates():
    """run_agent returns early when discovery finds no candidates."""
    discovery_result = {
        "id": "empty-2024",
        "candidates": [],
    }

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("empty-2024", cheap_mode=True)

    assert result["id"] == "empty-2024"
    assert result["candidates"] == []
    # Only 1 call (discovery), no issue research or refinement
    assert mock_loop.call_count == 1


@pytest.mark.asyncio
async def test_run_agent_update_mode():
    """run_agent with existing data runs in update mode."""
    existing = {"id": "test-2024", "candidates": [], "updated_utc": "2024-01-01"}
    updated = {"id": "test-2024", "candidates": [{"name": "Bob", "issues": {}}]}

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        mock_loop.return_value = updated
        result = await run_agent("test-2024", cheap_mode=True)

    assert result["id"] == "test-2024"
    # update call + image resolution for Bob = 2 calls
    assert mock_loop.call_count == 2


@pytest.mark.asyncio
async def test_run_agent_force_fresh_with_empty_dict():
    """run_agent with existing_data={} forces fresh run."""
    discovery_result = {
        "id": "test-2024",
        "candidates": [],
    }

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = minimal
        result = await run_agent("race-2024", cheap_mode=True, existing_data={})

    assert result["id"] == "race-2024"
    assert "updated_utc" in result
    assert result["generator"] == ["gpt-5.4-mini"]


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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("ts-2024", cheap_mode=True, existing_data={})

    source = result["candidates"][0]["issues"]["Healthcare"]["sources"][0]
    assert "last_accessed" in source


@pytest.mark.asyncio
async def test_run_agent_adds_donor_source_timestamps():
    """run_agent adds last_accessed to donor sources that lack it."""
    discovery_result = {
        "id": "donors-2024",
        "candidates": [
            {
                "name": "Alice",
                "issues": {},
                "top_donors": [
                    {
                        "name": "Example PAC",
                        "amount": 5000,
                        "source": {
                            "url": "https://example.com/donors",
                            "type": "news",
                            "title": "Donor report",
                        },
                    }
                ],
            }
        ],
    }

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("donors-2024", cheap_mode=True, existing_data={})

    donor_source = result["candidates"][0]["top_donors"][0]["source"]
    assert "last_accessed" in donor_source


@pytest.mark.asyncio
async def test_run_agent_model_selection():
    """run_agent selects gpt-5.4-mini in cheap mode and gpt-5.4 otherwise."""
    discovery_result = {"id": "m-2024", "candidates": []}

    for cheap_mode, expected_model in [(True, "gpt-5.4-mini"), (False, "gpt-5.4")]:
        with (
            patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        await run_agent("log-2024", cheap_mode=True, existing_data={}, on_log=on_log)

    # Should have at least "New research" and "Agent finished" messages
    assert len(log_messages) >= 2
    assert any("New research" in msg for _, msg in log_messages)
    assert any("finished" in msg for _, msg in log_messages)


# ---------------------------------------------------------------------------
# Handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v2_handler_raises_on_missing_race_id():
    """AgentHandler raises ValueError when race_id is missing."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    with pytest.raises(ValueError, match="Missing 'race_id'"):
        await handler.handle({}, {})


@pytest.mark.asyncio
async def test_v2_handler_runs_agent_and_publishes():
    """AgentHandler calls run_agent and publishes the result."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    fake_result = {"id": "test-race", "candidates": []}

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_publish", new_callable=AsyncMock) as mock_publish,
    ):
        mock_agent.return_value = fake_result
        mock_publish.return_value = Path("/tmp/test-race.json")

        result = await handler.handle(
            {"race_id": "test-race"},
            {"cheap_mode": True},
        )

    assert result["race_id"] == "test-race"
    assert result["status"] == "published"
    mock_agent.assert_called_once()


# ---------------------------------------------------------------------------
# New feature tests: review prompts, career/image fields, multi-LLM review
# ---------------------------------------------------------------------------


def test_review_prompt_exists():
    """Review prompts are defined and contain expected content."""
    from pipeline_client.agent.prompts import REVIEW_SYSTEM, REVIEW_USER

    assert "fact-checking" in REVIEW_SYSTEM.lower()
    assert "{race_id}" in REVIEW_USER
    assert "{profile_json}" in REVIEW_USER
    assert "verdict" in REVIEW_USER


def test_discovery_prompt_asks_for_career():
    """Discovery prompt includes career history request."""
    assert "career" in DISCOVERY_USER.lower()
    assert "career_history" in DISCOVERY_USER


def test_discovery_prompt_asks_for_education():
    """Discovery prompt includes education request."""
    assert "education" in DISCOVERY_USER.lower()


def test_discovery_prompt_asks_for_image():
    """Discovery prompt includes image/headshot request."""
    assert "image_url" in DISCOVERY_USER or "photo" in DISCOVERY_USER.lower()


def test_refine_prompt_asks_for_image():
    """Refine prompt includes image filling."""
    assert "image_url" in REFINE_USER or "headshot" in REFINE_USER.lower()


def test_shared_models_have_new_fields():
    """shared/models.py has CareerEntry, EducationEntry, VotingRecord, AgentReview."""
    from shared.models import AgentReview, Candidate, CareerEntry, EducationEntry, RaceJSON, ReviewFlag, VotingRecord

    # CareerEntry
    entry = CareerEntry(title="Senator")
    assert entry.title == "Senator"
    assert entry.organization is None

    # EducationEntry
    edu = EducationEntry(institution="MIT", degree="BS")
    assert edu.institution == "MIT"

    # VotingRecord
    vr = VotingRecord(bill_name="HR-1", vote="yes")
    assert vr.vote == "yes"

    # Candidate has new fields
    c = Candidate(name="Test")
    assert c.career_history == []
    assert c.education == []
    assert c.voting_record == []
    assert c.image_url is None

    # AgentReview
    review = AgentReview(
        model="claude-sonnet-4-6",
        reviewed_at="2024-01-01T00:00:00",
        verdict="approved",
    )
    assert review.verdict == "approved"
    assert review.flags == []

    # ReviewFlag
    flag = ReviewFlag(field="test.field", concern="inaccurate")
    assert flag.severity == "warning"

    # RaceJSON has reviews
    race = RaceJSON(
        id="test",
        election_date="2024-11-05",
        candidates=[],
        updated_utc="2024-01-01T00:00:00",
    )
    assert race.reviews == []


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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("new-fields-2024", cheap_mode=True, existing_data={})

    candidate = result["candidates"][0]
    assert candidate["image_url"] is None
    assert candidate["career_history"] == []
    assert candidate["education"] == []
    assert candidate["voting_record"] == []
    assert candidate["top_donors"] == []


@pytest.mark.asyncio
async def test_run_agent_enable_review_false():
    """run_agent with enable_review=False skips reviews."""
    discovery_result = {"id": "no-review-2024", "candidates": []}

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("no-review-2024", cheap_mode=True, existing_data={}, enable_review=False)

    assert result.get("reviews") == []


@pytest.mark.asyncio
async def test_run_agent_enable_review_skips_without_keys():
    """run_agent with enable_review=True skips providers without API keys."""
    discovery_result = {"id": "review-2024", "candidates": []}

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("GEMINI_API_KEY", None)

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch.dict(os.environ, env, clear=True),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("review-2024", cheap_mode=True, existing_data={}, enable_review=True)

    # No reviews because no API keys are set
    assert result.get("reviews") == []


@pytest.mark.asyncio
async def test_run_single_review_claude():
    """_run_single_review with claude returns structured review."""
    from pipeline_client.agent.agent import DEFAULT_CLAUDE_MODEL, _run_single_review

    review_response = json.dumps(
        {
            "verdict": "approved",
            "summary": "Looks good.",
            "flags": [],
        }
    )

    with (
        patch("pipeline_client.agent.agent._call_anthropic", new_callable=AsyncMock) as mock_claude,
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
    ):
        mock_claude.return_value = review_response
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="claude")

    assert result is not None
    assert result["verdict"] == "approved"
    assert result["model"] == DEFAULT_CLAUDE_MODEL


@pytest.mark.asyncio
async def test_run_single_review_gemini():
    """_run_single_review with gemini returns structured review."""
    from pipeline_client.agent.agent import DEFAULT_GEMINI_MODEL, _run_single_review

    review_response = json.dumps(
        {
            "verdict": "flagged",
            "summary": "Found issues.",
            "flags": [{"field": "test", "concern": "bad", "severity": "warning"}],
        }
    )

    with (
        patch("pipeline_client.agent.agent._call_gemini", new_callable=AsyncMock) as mock_gemini,
        patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
    ):
        mock_gemini.return_value = review_response
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="gemini")

    assert result is not None
    assert result["verdict"] == "flagged"
    assert len(result["flags"]) == 1


@pytest.mark.asyncio
async def test_run_single_review_handles_failure():
    """_run_single_review returns None on failure."""
    from pipeline_client.agent.agent import _run_single_review

    with (
        patch("pipeline_client.agent.agent._call_anthropic", new_callable=AsyncMock) as mock_claude,
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
    ):
        mock_claude.side_effect = RuntimeError("API down")
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="claude")

    assert result is None


@pytest.mark.asyncio
async def test_v2_handler_passes_enable_review():
    """AgentHandler passes enable_review option to run_agent."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    fake_result = {"id": "test-race", "candidates": []}

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_publish", new_callable=AsyncMock) as mock_publish,
    ):
        mock_agent.return_value = fake_result
        mock_publish.return_value = Path("/tmp/test-race.json")

        await handler.handle(
            {"race_id": "test-race"},
            {"cheap_mode": True, "enable_review": True},
        )

    mock_agent.assert_called_once()
    call_kwargs = mock_agent.call_args
    assert call_kwargs.kwargs["enable_review"] is True
