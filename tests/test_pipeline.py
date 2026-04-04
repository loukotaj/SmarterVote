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

from pipeline_client.agent.agent import (
    SEARCH_TOOL,
    _agent_loop,
    _extract_json,
    _fetch_page,
    _is_unusable_page_text,
    _load_existing,
    _select_target_candidates,
    _serper_search,
    run_agent,
)
from pipeline_client.agent.prompts import (
    CANONICAL_ISSUES,
    DISCOVERY_SYSTEM,
    DISCOVERY_USER,
    ISSUE_RESEARCH_SYSTEM,
    ISSUE_RESEARCH_USER,
    ISSUE_SUBAGENT_SYSTEM,
    ISSUE_SUBAGENT_USER,
    REFINE_SYSTEM,
    REFINE_USER,
    ROSTER_SYNC_SYSTEM,
    ROSTER_SYNC_USER,
    UPDATE_ISSUE_SUBAGENT_SYSTEM,
    UPDATE_ISSUE_SUBAGENT_USER,
    UPDATE_ISSUE_SYSTEM,
    UPDATE_ISSUE_USER,
    UPDATE_META_SYSTEM,
    UPDATE_META_USER,
)

# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_canonical_issues_count():
    """All canonical issues are defined."""
    assert len(CANONICAL_ISSUES) == 12


def test_canonical_issues_no_duplicates():
    """No duplicate canonical issues."""
    assert len(CANONICAL_ISSUES) == len(set(CANONICAL_ISSUES))


def test_canonical_issues_thematic_order():
    """Canonical issues are in the expected thematic order."""
    assert CANONICAL_ISSUES[0] == "Economy"
    assert CANONICAL_ISSUES[-1] == "Local Issues"


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
    """Refine user prompt accepts race_id, candidate_name, candidate_json, and other params."""
    result = REFINE_USER.format(
        race_id="mo-senate-2024",
        candidate_name="Jane Doe",
        candidate_json='{"name": "Jane Doe"}',
        race_description="A senate race.",
        other_candidates="John Smith",
        all_issues="Healthcare, Economy",
    )
    assert "mo-senate-2024" in result
    assert "Jane Doe" in result
    assert "Healthcare, Economy" in result


def test_update_meta_user_formats():
    """Update meta prompt accepts race_id, candidate_names, and last_updated."""
    result = UPDATE_META_USER.format(
        race_id="mo-senate-2024",
        candidate_names="Alice, Bob",
        last_updated="2024-01-01T00:00:00Z",
    )
    assert "mo-senate-2024" in result
    assert "2024-01-01" in result


def test_discovery_prompt_mentions_donor_sources():
    """Discovery prompt tells the model to include donor summary and links."""
    result = DISCOVERY_USER.format(race_id="mo-senate-2024")
    assert "donor_summary" in result
    assert "links" in result


def test_refine_prompt_mentions_donor_sources():
    """Refine prompt asks agent to fill donor_summary using set_donor_summary."""
    result = REFINE_USER.format(
        race_id="mo-senate-2024",
        candidate_name="Jane Doe",
        candidate_json='{"name": "Jane Doe"}',
        race_description="A senate race.",
        other_candidates="John Smith",
        all_issues="Healthcare, Economy",
    )
    assert "set_donor_summary" in result


def test_update_prompt_mentions_donor_sources():
    """Update meta prompt uses donor_summary instead of top_donors."""
    result = UPDATE_META_USER.format(
        race_id="mo-senate-2024",
        candidate_names="Alice, Bob",
        last_updated="2024-01-01T00:00:00Z",
    )
    assert "donor_summary" in result
    assert "top_donors" not in result


def test_prompts_contain_rules():
    """All system prompts include shared rules."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_RESEARCH_SYSTEM, REFINE_SYSTEM, UPDATE_META_SYSTEM, UPDATE_ISSUE_SYSTEM]:
        assert "nonpartisan" in prompt.lower()
        assert "web_search" in prompt


def test_prompts_mention_confidence_levels():
    """All system prompts describe the confidence levels."""
    for prompt in [DISCOVERY_SYSTEM, ISSUE_RESEARCH_SYSTEM, REFINE_SYSTEM, UPDATE_META_SYSTEM, UPDATE_ISSUE_SYSTEM]:
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
            "donor_summary": None,
            "links": [],
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


def _mock_openai_response(content=None, tool_calls=None, finish_reason="stop"):
    """Build a mock object mimicking the OpenAI SDK ChatCompletion response."""
    fn_mocks = []
    if tool_calls:
        for tc in tool_calls:
            fn_mock = MagicMock()
            fn_mock.name = tc["function"]["name"]
            fn_mock.arguments = tc["function"]["arguments"]
            tc_mock = MagicMock()
            tc_mock.id = tc["id"]
            tc_mock.function = fn_mock
            fn_mocks.append(tc_mock)

    message = MagicMock()
    message.content = content
    message.tool_calls = fn_mocks or None
    message.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_agent_loop_produces_json():
    """_agent_loop returns parsed JSON when model gives a direct answer."""
    response = _mock_openai_response(content=json.dumps({"result": "ok"}))
    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.return_value = response
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_agent_loop_handles_tool_calls():
    """_agent_loop executes tool calls then returns final JSON."""
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {
                    "name": "web_search",
                    "arguments": json.dumps({"query": "test"}),
                },
            }
        ],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

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
    tool_response = _mock_openai_response(
        tool_calls=[
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
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

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
    bad = _mock_openai_response(content="not json")
    good = _mock_openai_response(content=json.dumps({"ok": True}))

    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.side_effect = [bad, good]
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"ok": True}
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_raises_on_max_iterations():
    """_agent_loop raises RuntimeError when max iterations reached."""
    bad = _mock_openai_response(content="still not json")

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
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {
                    "name": "web_search",
                    "arguments": json.dumps({"query": "test"}),
                },
            }
        ],
    )
    final_response = _mock_openai_response(content=json.dumps({"ok": True}))

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


def test_is_unusable_page_text_detects_block_pages():
    """Blocked placeholder content is treated as unusable."""
    blocked = "Please enable JavaScript to continue. Attention required by security check."
    assert _is_unusable_page_text(blocked) is True


@pytest.mark.asyncio
async def test_fetch_page_uses_proxy_fallback_when_primary_unusable():
    """_fetch_page falls back to proxy when direct fetch is too short/useless."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(
        side_effect=[
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            _Resp("Proxy recovered page text " + ("x" * 500), "text/plain"),
        ]
    )

    with (
        patch("pipeline_client.agent.agent._get_search_cache", return_value=None),
        patch("pipeline_client.agent.agent._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page("https://www.example.com/issues")

    assert "Proxy recovered page text" in result
    assert "[Failed to fetch" not in result


@pytest.mark.asyncio
async def test_fetch_page_attempts_jeff_wadlin_issues_url():
    """_fetch_page issues a direct request to the exact Wadlin issues URL."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    target_url = "https://www.jeffwadlin.com/issues"
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=_Resp("Valid issue content " + ("x" * 500)))

    with (
        patch("pipeline_client.agent.agent._get_search_cache", return_value=None),
        patch("pipeline_client.agent.agent._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(target_url)

    requested_urls = [call.args[0] for call in mock_client.get.call_args_list if call.args]
    assert requested_urls[0] == target_url, "First HTTP call must be directly to the Wadlin issues URL"
    assert "Valid issue content" in result


@pytest.mark.asyncio
async def test_fetch_page_jeff_wadlin_blocked_falls_back_to_proxy_with_correct_url():
    """When jeffwadlin.com returns a JS stub (~214 chars), _fetch_page retries via jina proxy
    using the original https:// URL (not a downgraded http:// version)."""

    class _Resp:
        def __init__(self, text: str, content_type: str = "text/html; charset=utf-8"):
            self.text = text
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    target_url = "https://www.jeffwadlin.com/issues"
    expected_proxy_url = f"https://r.jina.ai/{target_url}"
    proxy_content = "Healthcare: I support a universal 80/20 Medicare-for-all option. " + ("x" * 400)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(
        side_effect=[
            # Both direct header profiles return a tiny JS shell (~214 chars after stripping)
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            _Resp("<html><body>Please enable JavaScript</body></html>"),
            # Jina proxy returns real content
            _Resp(proxy_content, "text/plain"),
        ]
    )

    with (
        patch("pipeline_client.agent.agent._get_search_cache", return_value=None),
        patch("pipeline_client.agent.agent._get_fetch_client", return_value=mock_client),
    ):
        result = await _fetch_page(target_url)

    requested_urls = [call.args[0] for call in mock_client.get.call_args_list if call.args]
    assert requested_urls[0] == target_url, "First call must be the direct Wadlin issues URL"
    assert expected_proxy_url in requested_urls, f"Proxy call must use the original https:// URL — got: {requested_urls}"
    assert "Medicare-for-all" in result
    assert "[Failed to fetch" not in result


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

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        # discovery (json) → returns skeleton
        # image resolution (1 candidate) → returns {}
        # 12 issue sub-agent calls (tools mode) → return {}
        # finance/voting (json) → return {}
        # per-candidate refine (1, tools mode) → return {}
        # meta refine (tools mode) → return {}
        # Total: 1 + 1 + 12 + 1 + 1 + 1 = 17
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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
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
async def test_run_agent_update_mode():
    """run_agent with existing data but no candidates falls back to fresh run."""
    existing = {"id": "test-2024", "candidates": [], "updated_utc": "2024-01-01"}
    updated = {"id": "test-2024", "candidates": [{"name": "Bob", "issues": {}}]}

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        # existing has no candidates → falls back to _run_fresh:
        # discovery + image (Bob) + 12 issue sub-agents + finance + refine + meta refine = 17
        mock_loop.return_value = {}
        mock_loop.side_effect = [updated, {"image_url": None}] + [{}] * 15
        result = await run_agent(
            "test-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["id"] == "test-2024"
    # Falls back to fresh: 1 + 1 + 12 + 1 + 1 + 1 = 17
    assert mock_loop.call_count == 17


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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
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
            }
        ],
    }

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("donors-2024", cheap_mode=True, existing_data={})

    candidate = result["candidates"][0]
    assert candidate["donor_summary"] == "Alice received most funding from tech industry PACs."
    assert candidate["donor_source_url"] == "https://example.com/donors"


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
    """AgentHandler calls run_agent and saves draft."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    fake_result = {"id": "test-race", "candidates": []}

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
    ):
        mock_agent.return_value = fake_result
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        result = await handler.handle(
            {"race_id": "test-race"},
            {"cheap_mode": True},
        )

    assert result["race_id"] == "test-race"
    assert result["status"] == "draft"
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
    """shared/models.py has CareerEntry, EducationEntry, CandidateLink, AgentReview."""
    from shared.models import AgentReview, Candidate, CandidateLink, CareerEntry, EducationEntry, RaceJSON, ReviewFlag

    # CareerEntry
    entry = CareerEntry(title="Senator")
    assert entry.title == "Senator"
    assert entry.organization is None

    # EducationEntry
    edu = EducationEntry(institution="MIT", degree="BS")
    assert edu.institution == "MIT"

    # CandidateLink replaces VotingRecord / TopDonor
    link = CandidateLink(url="https://ballotpedia.org/Alice", title="Alice on Ballotpedia", type="ballotpedia")
    assert link.url.startswith("https://")

    # Candidate has new fields
    c = Candidate(name="Test")
    assert c.career_history == []
    assert c.education == []
    assert c.links == []
    assert c.donor_summary is None
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

    # RaceJSON has reviews and polling_note
    race = RaceJSON(
        id="test",
        election_date="2024-11-05",
        candidates=[],
        updated_utc="2024-01-01T00:00:00",
    )
    assert race.reviews == []
    assert race.polling_note is None


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
    assert candidate["donor_summary"] is None
    assert candidate["links"] == []


@pytest.mark.asyncio
async def test_run_agent_skips_reviews_when_step_disabled():
    """run_agent skips reviews when the review step is disabled."""
    discovery_result = {"id": "no-review-2024", "candidates": []}

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
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
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch.dict(os.environ, env, clear=True),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent("review-2024", cheap_mode=True, existing_data={})

    # No reviews because no API keys are set
    assert result.get("reviews") == []


@pytest.mark.asyncio
async def test_run_single_review_claude():
    """_run_single_review with claude returns structured review."""
    from pipeline_client.agent.review import DEFAULT_CLAUDE_MODEL, _run_single_review

    review_response = json.dumps(
        {
            "verdict": "approved",
            "summary": "Looks good.",
            "flags": [],
        }
    )

    with (
        patch("pipeline_client.agent.review._call_anthropic", new_callable=AsyncMock) as mock_claude,
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
    from pipeline_client.agent.review import DEFAULT_GEMINI_MODEL, _run_single_review

    review_response = json.dumps(
        {
            "verdict": "flagged",
            "summary": "Found issues.",
            "flags": [{"field": "test", "concern": "bad", "severity": "warning"}],
        }
    )

    with (
        patch("pipeline_client.agent.review._call_gemini", new_callable=AsyncMock) as mock_gemini,
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
    from pipeline_client.agent.review import _run_single_review

    with (
        patch("pipeline_client.agent.review._call_anthropic", new_callable=AsyncMock) as mock_claude,
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
    ):
        mock_claude.side_effect = RuntimeError("API down")
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="claude")

    assert result is None


@pytest.mark.asyncio
async def test_v2_handler_passes_enabled_steps():
    """AgentHandler passes enabled_steps option to run_agent."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    fake_result = {"id": "test-race", "candidates": []}

    with (
        patch("pipeline_client.agent.agent.run_agent", new_callable=AsyncMock) as mock_agent,
        patch.object(handler, "_save_draft", new_callable=AsyncMock) as mock_save_draft,
    ):
        mock_agent.return_value = fake_result
        mock_save_draft.return_value = Path("/tmp/test-race.json")

        await handler.handle(
            {"race_id": "test-race"},
            {
                "cheap_mode": True,
                "enabled_steps": ["discovery", "images", "issues"],
                "candidate_names": ["Jeff Wadlin"],
            },
        )

    mock_agent.assert_called_once()
    call_kwargs = mock_agent.call_args
    assert call_kwargs.kwargs["enabled_steps"] == ["discovery", "images", "issues"]
    assert call_kwargs.kwargs["candidate_names"] == ["Jeff Wadlin"]


# ---------------------------------------------------------------------------
# New architecture tests — tools mode, roster sync, per-issue sub-agent
# ---------------------------------------------------------------------------


def test_roster_sync_prompt_formats():
    """Roster sync prompt accepts race_id, last_updated, candidate_names."""
    result = ROSTER_SYNC_USER.format(
        race_id="ga-senate-2026",
        last_updated="2025-01-01T00:00:00Z",
        candidate_names="Alice, Bob",
    )
    assert "ga-senate-2026" in result
    assert "Alice, Bob" in result
    assert "add_candidate" in result


def test_issue_subagent_prompt_formats():
    """Issue sub-agent prompt accepts required variables."""
    result = ISSUE_SUBAGENT_USER.format(
        candidate_name="Jane Doe",
        race_id="mi-senate-2026",
        issue="Healthcare",
        candidate_website="https://example.com/",
        candidate_issue_urls="https://example.com/issues",
        handoff_context="No prior context available.",
    )
    assert "Jane Doe" in result
    assert "Healthcare" in result
    assert "https://example.com/issues" in result
    assert "set_issue_stance" in result


def test_update_issue_subagent_prompt_formats():
    """Update issue sub-agent prompt accepts required variables."""
    result = UPDATE_ISSUE_SUBAGENT_USER.format(
        candidate_name="Jane Doe",
        race_id="mi-senate-2026",
        issue="Healthcare",
        last_updated="2025-01-01T00:00:00Z",
        existing_stance="  Stance: Supports ACA.\n  Confidence: high",
        candidate_website="https://example.com/",
        candidate_issue_urls="https://example.com/issues",
        handoff_context="No prior context available.",
    )
    assert "Jane Doe" in result
    assert "Healthcare" in result
    assert "Supports ACA" in result
    assert "https://example.com/issues" in result


def test_select_target_candidates_case_insensitive():
    """Candidate targeting matches names case-insensitively and returns canonical names."""
    selected = _select_target_candidates(
        ["Tom Cotton", "Jeff Wadlin"],
        ["jeff wadlin"],
        log=lambda *_: None,
    )
    assert selected == ["Jeff Wadlin"]


def test_editing_tool_schemas_exist():
    """All editing tool schemas are importable from agent module."""
    from pipeline_client.agent.agent import (
        ADD_CANDIDATE_TOOL,
        ADD_LINK_TOOL,
        ADD_POLL_TOOL,
        CANDIDATE_TOOLS,
        ISSUE_TOOLS,
        RACE_TOOLS,
        READ_PROFILE_TOOL,
        RECORD_TOOLS,
        REMOVE_CANDIDATE_TOOL,
        RENAME_CANDIDATE_TOOL,
        ROSTER_TOOLS,
        SET_CANDIDATE_FIELD_TOOL,
        SET_CANDIDATE_SUMMARY_TOOL,
        SET_DONOR_SUMMARY_TOOL,
        SET_ISSUE_STANCE_TOOL,
        SET_VOTING_SUMMARY_TOOL,
        UPDATE_RACE_FIELD_TOOL,
    )

    assert len(ROSTER_TOOLS) == 3
    assert len(CANDIDATE_TOOLS) == 2
    assert len(ISSUE_TOOLS) == 1
    assert len(RECORD_TOOLS) == 3  # donor_summary, voting_summary, add_link
    assert len(RACE_TOOLS) == 2
    assert READ_PROFILE_TOOL["function"]["name"] == "read_profile"


def test_make_editing_handlers():
    """_make_editing_handlers returns all expected handler functions."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [], "polling": []}
    log = lambda level, msg: None
    handlers = _make_editing_handlers(race_json, log)

    expected_names = {
        "add_candidate",
        "remove_candidate",
        "rename_candidate",
        "set_candidate_field",
        "set_candidate_summary",
        "set_issue_stance",
        "set_donor_summary",
        "set_voting_summary",
        "add_candidate_link",
        "add_poll",
        "update_race_field",
        "read_profile",
        "add_education_entry",
        "update_education_entry",
        "add_career_entry",
        "remove_career_entry",
        "update_career_entry",
        "set_social_media",
        "clear_education",
        "clear_career_history",
    }
    assert set(handlers.keys()) == expected_names


def test_add_candidate_handler():
    """add_candidate handler adds a candidate to race_json."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": []}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["add_candidate"]({"name": "Alice", "party": "Democratic"})
    assert "Added" in result
    assert len(race_json["candidates"]) == 1
    assert race_json["candidates"][0]["name"] == "Alice"


def test_remove_candidate_handler():
    """remove_candidate handler soft-deletes a candidate (marks withdrawn, keeps in list)."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "D"}, {"name": "Bob", "party": "R"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"]({"name": "Alice", "reason": "withdrew"})
    assert "withdrawn" in result.lower()
    # Soft-delete: candidate stays in the list but is flagged
    assert len(race_json["candidates"]) == 2
    alice = next(c for c in race_json["candidates"] if c["name"] == "Alice")
    assert alice.get("withdrawn") is True
    assert alice.get("withdrawal_reason") == "withdrew"


def test_set_issue_stance_handler():
    """set_issue_stance handler writes a stance to candidate issues."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "issues": {}}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["set_issue_stance"](
        {
            "candidate_name": "Alice",
            "issue": "Healthcare",
            "stance": "Supports universal coverage.",
            "confidence": "high",
            "sources": [{"url": "https://example.com", "type": "news", "title": "Article"}],
        }
    )
    assert "Healthcare" in result
    assert race_json["candidates"][0]["issues"]["Healthcare"]["stance"] == "Supports universal coverage."


def test_read_profile_handler():
    """read_profile handler returns JSON for different sections."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "id": "test",
        "description": "A test race",
        "candidates": [{"name": "Alice", "issues": {"Healthcare": {"stance": "Yes", "confidence": "high"}}}],
        "polling": [],
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    meta = handlers["read_profile"]({"section": "meta"})
    assert "test" in meta
    assert "description" in meta

    issues = handlers["read_profile"]({"section": "issues"})
    assert "Healthcare" in issues


@pytest.mark.asyncio
async def test_agent_loop_tools_mode():
    """_agent_loop in tools_mode returns {} when model stops calling tools."""
    response = _mock_openai_response(content="All done, edits committed.")
    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.return_value = response
        result = await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test-tools",
            tools_mode=True,
        )
    assert result == {}


@pytest.mark.asyncio
async def test_agent_loop_tools_mode_calls_extra_handlers():
    """_agent_loop in tools_mode dispatches extra tool handlers."""
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {
                    "name": "set_issue_stance",
                    "arguments": json.dumps(
                        {
                            "candidate_name": "Alice",
                            "issue": "Healthcare",
                            "stance": "Supports ACA",
                            "confidence": "high",
                        }
                    ),
                },
            }
        ],
    )
    done_response = _mock_openai_response(content="Done.")

    handler_called = {}

    def fake_handler(args):
        handler_called.update(args)
        return "OK"

    with patch("pipeline_client.agent.agent._call_openai", new_callable=AsyncMock) as mock:
        mock.side_effect = [tool_response, done_response]
        result = await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test-tools",
            tools_mode=True,
            extra_tools=[{"type": "function", "function": {"name": "set_issue_stance", "parameters": {}}}],
            extra_tool_handlers={"set_issue_stance": fake_handler},
        )

    assert result == {}
    assert handler_called["candidate_name"] == "Alice"
    assert handler_called["issue"] == "Healthcare"


def test_search_cache_list_cached_for_race():
    """SearchCache.list_cached_for_race returns cached queries."""
    import tempfile

    from pipeline_client.agent.search_cache import SearchCache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = SearchCache(cache_dir=tmpdir, default_ttl_hours=168)
        cache.set("test query", [{"title": "R", "snippet": "...", "url": "https://r.com"}], race_id="test-race")

        result = cache.list_cached_for_race("test-race")
        assert len(result["searches"]) == 1
        assert result["searches"][0]["query"] == "test query"
        assert "https://r.com" in result["searches"][0]["urls"]


@pytest.mark.asyncio
async def test_run_agent_update_with_candidates():
    """run_agent in update mode with existing candidates runs roster sync + tools phases."""
    existing = {
        "id": "test-2024",
        "candidates": [{"name": "Alice", "party": "D", "issues": {}}],
        "updated_utc": "2024-01-01T00:00:00Z",
    }

    with (
        patch("pipeline_client.agent.agent._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=existing),
    ):
        # roster sync (tools) → {}
        # meta update (tools) → {}
        # image resolution (1 candidate, agent fallback) → {}
        # 12 issue sub-agents (tools) → {} each
        # finance (json) → {}
        # refine per-candidate (tools) → {}
        # refine meta (tools) → {}
        # Total: 1 + 1 + 1 + 12 + 1 + 1 + 1 = 18
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
