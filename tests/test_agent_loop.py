"""Tests for the _agent_loop function (direct answers, tool calls, retries, tools mode)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError

from pipeline_client.agent.agent import _agent_loop
from pipeline_client.agent.errors import RetryableProviderError
from pipeline_client.agent.llm import _await_with_run_budget, _call_openrouter, _provider_usage_cost
from pipeline_client.agent.model_registry import DEFAULT_RESEARCH_MODEL, SMALL_MODEL, escalation_for

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
    """Build a mock object mimicking the SDK ChatCompletion response."""
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


def test_provider_usage_cost_reads_openrouter_extra_field():
    usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "model_extra"])
    usage.model_extra = {"cost": 0.01234567}

    assert _provider_usage_cost(usage) == pytest.approx(0.01234567)


def test_provider_usage_cost_rejects_invalid_values():
    usage = MagicMock(spec=["cost", "model_extra"])
    usage.cost = "not-a-number"

    assert _provider_usage_cost(usage) is None


@pytest.mark.asyncio
async def test_tool_timeout_returns_recoverable_fallback():
    async def slow_tool():
        import asyncio

        await asyncio.sleep(1)

    with patch("pipeline_client.agent.llm.record_retry_metric") as record_retry:
        result = await _await_with_run_budget(
            slow_tool(),
            run_budget=None,
            requested_timeout=0.001,
            operation="test tool",
            timeout_result={"error": "timed out"},
        )

    assert result == {"error": "timed out"}
    record_retry.assert_called_once_with("deadline_exits")


# ---------------------------------------------------------------------------
# Standard mode tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_openrouter_retries_connection_error():
    """_call_openrouter retries transient SDK connection failures."""
    response = _mock_openai_response(content=json.dumps({"result": "ok"}))
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")),
            response,
        ]
    )

    with (
        patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client),
        patch("pipeline_client.agent.llm.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _call_openrouter(
            [{"role": "user", "content": "Return JSON."}],
            model="gpt-5.4-mini",
            max_retries=2,
        )

    assert result is response
    assert client.chat.completions.create.call_count == 2
    mock_sleep.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_call_openrouter_classifies_exhausted_connection_failure():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    )

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(RetryableProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "Return JSON."}],
                model="gpt-5.4-mini",
                max_retries=1,
            )

    assert raised.value.provider == "openrouter"
    assert raised.value.code == "connection_failed"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_agent_loop_produces_json():
    """_agent_loop returns parsed JSON when model gives a direct answer."""
    response = _mock_openai_response(content=json.dumps({"result": "ok"}))
    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
        mock.return_value = response
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_agent_loop_passes_phase_request_retry_limit():
    response = _mock_openai_response(content=json.dumps({"result": "ok"}))
    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
        mock.return_value = response
        await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test",
            max_request_retries=2,
        )

    assert mock.call_args.kwargs["max_retries"] == 2


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
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._serper_search", new_callable=AsyncMock) as mock_search,
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
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._serper_search", new_callable=AsyncMock) as mock_search,
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

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
        mock.side_effect = [bad, good]
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"ok": True}
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_raises_on_max_iterations():
    """_agent_loop raises RuntimeError when max iterations reached."""
    bad = _mock_openai_response(content="still not json")

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
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
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._serper_search", new_callable=AsyncMock) as mock_search,
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
# Tools mode tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_loop_tools_mode():
    """_agent_loop in tools_mode returns {} when model stops calling tools."""
    response = _mock_openai_response(content="All done, edits committed.")
    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
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

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
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


@pytest.mark.asyncio
async def test_narrow_issue_phase_rejects_full_profile_read():
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {
                    "name": "read_profile",
                    "arguments": json.dumps({"section": "full"}),
                },
            }
        ],
    )
    done_response = _mock_openai_response(content="Done.")
    handler = MagicMock(return_value=json.dumps(FAKE_RACE_JSON))

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
        mock.side_effect = [tool_response, done_response]
        await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="issue-Jane-Healthcare",
            tools_mode=True,
            extra_tools=[{"type": "function", "function": {"name": "read_profile", "parameters": {}}}],
            extra_tool_handlers={"read_profile": handler},
        )

    handler.assert_not_called()
    second_request = mock.call_args_list[1].args[0]
    assert any("Full-profile reads are not available" in str(message.get("content")) for message in second_request)


@pytest.mark.asyncio
async def test_agent_loop_handles_web_image_search_tool_call():
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {"name": "web_image_search", "arguments": json.dumps({"query": "candidate photo"})},
            }
        ],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._serper_image_search", new_callable=AsyncMock) as mock_image_search,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_image_search.return_value = [{"imageUrl": "https://example.com/x.jpg"}]

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"done": True}
    mock_image_search.assert_called_once_with("candidate photo", race_id=None)


@pytest.mark.asyncio
async def test_agent_loop_handles_fetch_page_tool_call():
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {"name": "fetch_page", "arguments": json.dumps({"url": "https://example.com/bio"})},
            }
        ],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("pipeline_client.agent.llm._page_fetch_log_hint", return_value=None),
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_fetch.return_value = "page body text"

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"done": True}
    mock_fetch.assert_called_once_with("https://example.com/bio")


@pytest.mark.asyncio
async def test_agent_loop_handles_ballotpedia_lookup_tool_call():
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {"name": "ballotpedia_lookup", "arguments": json.dumps({"candidate_name": "Jane Doe"})},
            }
        ],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._ballotpedia_lookup", new_callable=AsyncMock) as mock_lookup,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_lookup.return_value = {"found": True, "url": "https://ballotpedia.org/Jane_Doe"}

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"done": True}
    mock_lookup.assert_called_once_with("Jane Doe")


@pytest.mark.asyncio
async def test_agent_loop_handles_ballotpedia_election_lookup_tool_call():
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {"name": "ballotpedia_election_lookup", "arguments": json.dumps({})},
            }
        ],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._ballotpedia_election_lookup", new_callable=AsyncMock) as mock_lookup,
    ):
        mock_call.side_effect = [tool_response, final_response]
        mock_lookup.return_value = {"found": True, "candidates": [{"name": "Jane Doe"}]}

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test", race_id="fallback-race")

    assert result == {"done": True}
    # No explicit race_id arg in the tool call -> falls back to the loop's race_id.
    mock_lookup.assert_called_once_with("fallback-race")


@pytest.mark.asyncio
async def test_agent_loop_handles_unknown_tool_call():
    tool_response = _mock_openai_response(
        tool_calls=[{"id": "call_1", "function": {"name": "not_a_real_tool", "arguments": "{}"}}],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [tool_response, final_response]
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"done": True}
    # Second request must contain the tool error message for the unknown tool.
    second_request = mock_call.call_args_list[1].args[0]
    assert any("unknown tool" in str(m.get("content")) for m in second_request if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_agent_loop_tools_mode_extra_handler_exception_is_reported_as_error():
    tool_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_1",
                "function": {"name": "explode", "arguments": json.dumps({"x": 1})},
            }
        ],
    )
    done_response = _mock_openai_response(content="Done.")

    def exploding_handler(args):
        raise RuntimeError("handler blew up")

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [tool_response, done_response]
        result = await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test-tools",
            tools_mode=True,
            extra_tools=[{"type": "function", "function": {"name": "explode", "parameters": {}}}],
            extra_tool_handlers={"explode": exploding_handler},
        )

    assert result == {}
    second_request = mock_call.call_args_list[1].args[0]
    assert any("handler blew up" in str(m.get("content")) for m in second_request if m.get("role") == "tool")


@pytest.mark.asyncio
async def test_agent_loop_retries_on_truncated_response():
    """finish_reason='length' triggers a brevity-nudge retry rather than failing."""
    truncated = _mock_openai_response(content='{"partial": tr', finish_reason="length")
    complete = _mock_openai_response(content=json.dumps({"ok": True}), finish_reason="stop")

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [truncated, complete]
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"ok": True}
    assert mock_call.call_count == 2
    second_request = mock_call.call_args_list[1].args[0]
    assert any("too long" in str(m.get("content")) for m in second_request if m.get("role") == "user")


@pytest.mark.asyncio
async def test_agent_loop_raises_after_max_json_retries_exhausted():
    bad = _mock_openai_response(content="not json at all")

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = bad
        with pytest.raises(RuntimeError, match="failed to produce valid JSON"):
            await _agent_loop(
                "system",
                "user",
                model="gpt-5.4-mini",
                phase_name="test",
                max_iterations=10,
            )

    # _MAX_JSON_RETRIES is 3: the loop should give up well before max_iterations.
    assert mock_call.call_count == 3


@pytest.mark.asyncio
async def test_agent_loop_nudges_model_toward_final_answer_in_json_mode():
    tool_response = _mock_openai_response(
        tool_calls=[{"id": "call_1", "function": {"name": "web_search", "arguments": json.dumps({"query": "q"})}}],
    )
    final_response = _mock_openai_response(content=json.dumps({"done": True}))
    # max_iterations=3 -> nudge_at = max(int(3/1.5), 3) = 3, but loop only runs
    # while iteration < max_iterations, so use a slightly larger budget with a
    # tool call on each early iteration to reach the nudge point.
    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call,
        patch("pipeline_client.agent.llm._serper_search", new_callable=AsyncMock) as mock_search,
    ):
        mock_call.side_effect = [tool_response, tool_response, tool_response, final_response]
        mock_search.return_value = []

        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test", max_iterations=5)

    assert result == {"done": True}


@pytest.mark.asyncio
async def test_agent_loop_forces_required_tool_without_escalating_a_healthy_loop():
    final_response = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_final",
                "function": {
                    "name": "set_issue_stance",
                    "arguments": json.dumps({"stance": "No public position found"}),
                },
            }
        ]
    )
    handler = MagicMock(return_value="OK")
    final_tool = {
        "type": "function",
        "function": {"name": "set_issue_stance", "description": "Record result", "parameters": {"type": "object"}},
    }

    with (
        patch("pipeline_client.agent.llm.total_token_budget_reached", return_value=True),
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock, return_value=final_response) as call,
    ):
        result = await _agent_loop(
            "system",
            "user",
            model=SMALL_MODEL,
            phase_name="issue-test",
            tools_mode=True,
            extra_tools=[final_tool],
            extra_tool_handlers={"set_issue_stance": handler},
            required_final_tool_name="set_issue_stance",
            required_final_instruction="Choose a sourced stance or the exact absence marker.",
            return_tool_trace=True,
        )

    assert handler.call_count == 1
    # Hitting the token ceiling forces finalization but is not a stall, so the
    # closing turn — the largest prompt in the run — stays on the loop's own model.
    assert call.call_args.kwargs["model"] == SMALL_MODEL
    assert call.call_args.kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "set_issue_stance"},
    }
    assert result["_tool_trace"]["token_budget_reached"] is True


@pytest.mark.asyncio
async def test_agent_loop_does_not_accept_early_stop_before_required_final_tool():
    stopped = _mock_openai_response(content="Done")
    finalized = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_final",
                "function": {"name": "finalize_roster", "arguments": json.dumps({"summary": "Official list"})},
            }
        ]
    )
    handler = MagicMock(return_value="Roster finalized")
    final_tool = {
        "type": "function",
        "function": {"name": "finalize_roster", "description": "Finalize", "parameters": {"type": "object"}},
    }

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as call:
        call.side_effect = [stopped, finalized]
        result = await _agent_loop(
            "system",
            "user",
            model=DEFAULT_RESEARCH_MODEL,
            phase_name="roster-finalize-test",
            tools_mode=True,
            extra_tools=[final_tool],
            extra_tool_handlers={"finalize_roster": handler},
            required_final_tool_name="finalize_roster",
            required_final_instruction="Finalize the roster before stopping.",
            return_tool_trace=True,
        )

    assert call.call_count == 2
    assert handler.call_count == 1
    assert result["_tool_trace"]["required_final_tool_succeeded"] is True


@pytest.mark.asyncio
async def test_agent_loop_accepts_evidenced_no_change_after_one_search():
    source_url = "https://elections.example.gov/current-race"
    search = _mock_openai_response(
        tool_calls=[{"id": "search", "function": {"name": "web_search", "arguments": json.dumps({"query": "race update"})}}]
    )
    finish = _mock_openai_response(
        tool_calls=[
            {
                "id": "finish",
                "function": {
                    "name": "finish_no_changes",
                    "arguments": json.dumps({"reason": "Current results match the profile", "evidence_url": source_url}),
                },
            }
        ]
    )

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock, side_effect=[search, finish]),
        patch(
            "pipeline_client.agent.llm._serper_search",
            new_callable=AsyncMock,
            return_value=[{"title": "Current race", "url": source_url}],
        ),
    ):
        result = await _agent_loop(
            "system",
            "user",
            model=SMALL_MODEL,
            tools_mode=True,
            max_iterations=4,
            required_final_tool_name="finalize_roster",
            extra_tools=[
                {
                    "type": "function",
                    "function": {"name": "finalize_roster", "parameters": {"type": "object", "properties": {}}},
                }
            ],
            extra_tool_handlers={"finalize_roster": lambda _args: "ok"},
            allow_no_change_after_search=True,
            return_tool_trace=True,
        )

    assert result["_tool_trace"]["no_change_confirmed"] is True
    assert result["_tool_trace"]["search_calls"] == 1
    assert result["_tool_trace"]["required_final_tool_succeeded"] is False


@pytest.mark.asyncio
async def test_agent_loop_continues_normally_after_second_search():
    source_urls = ["https://example.gov/result-1", "https://example.gov/result-2"]
    searches = [
        _mock_openai_response(
            tool_calls=[
                {"id": f"search-{index}", "function": {"name": "web_search", "arguments": json.dumps({"query": query})}}
            ]
        )
        for index, query in enumerate(("race update", "candidate filing"), start=1)
    ]
    rejected_shortcut = _mock_openai_response(
        tool_calls=[
            {
                "id": "finish",
                "function": {
                    "name": "finish_no_changes",
                    "arguments": json.dumps({"reason": "No change", "evidence_url": source_urls[1]}),
                },
            }
        ]
    )
    finalized = _mock_openai_response(
        tool_calls=[{"id": "finalize", "function": {"name": "finalize_roster", "arguments": "{}"}}]
    )

    with (
        patch(
            "pipeline_client.agent.llm._call_openrouter",
            new_callable=AsyncMock,
            side_effect=[*searches, rejected_shortcut, finalized],
        ),
        patch(
            "pipeline_client.agent.llm._serper_search",
            new_callable=AsyncMock,
            side_effect=[[{"url": url}] for url in source_urls],
        ),
    ):
        result = await _agent_loop(
            "system",
            "user",
            model=SMALL_MODEL,
            tools_mode=True,
            max_iterations=5,
            required_final_tool_name="finalize_roster",
            extra_tools=[
                {
                    "type": "function",
                    "function": {"name": "finalize_roster", "parameters": {"type": "object", "properties": {}}},
                }
            ],
            extra_tool_handlers={"finalize_roster": lambda _args: "ok"},
            allow_no_change_after_search=True,
            return_tool_trace=True,
        )

    assert result["_tool_trace"]["search_calls"] == 2
    assert result["_tool_trace"]["no_change_confirmed"] is False
    assert result["_tool_trace"]["required_final_tool_succeeded"] is True


@pytest.mark.asyncio
async def test_agent_loop_reserves_edit_turn_before_forced_finalization():
    searched = _mock_openai_response(
        tool_calls=[
            {"id": "search", "function": {"name": "web_search", "arguments": json.dumps({"query": "official roster"})}}
        ]
    )
    edited = _mock_openai_response(
        tool_calls=[{"id": "edit", "function": {"name": "set_sources", "arguments": json.dumps({"name": "Alice"})}}]
    )
    finalized = _mock_openai_response(
        tool_calls=[
            {
                "id": "final",
                "function": {"name": "finalize_roster", "arguments": json.dumps({"summary": "Official roster"})},
            }
        ]
    )
    edit_tool = {
        "type": "function",
        "function": {"name": "set_sources", "description": "Set", "parameters": {"type": "object"}},
    }
    final_tool = {
        "type": "function",
        "function": {"name": "finalize_roster", "description": "Finalize", "parameters": {"type": "object"}},
    }

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as call,
        patch("pipeline_client.agent.llm._serper_search", new_callable=AsyncMock, return_value=[]),
    ):
        call.side_effect = [searched, edited, finalized]
        result = await _agent_loop(
            "system",
            "user",
            model=DEFAULT_RESEARCH_MODEL,
            phase_name="roster-final-turns",
            max_iterations=3,
            tools_mode=True,
            extra_tools=[edit_tool, final_tool],
            extra_tool_handlers={"set_sources": lambda _args: "OK", "finalize_roster": lambda _args: "OK"},
            required_final_tool_name="finalize_roster",
            escalate_on_tool_errors=True,
            return_tool_trace=True,
        )

    assert result["_tool_trace"]["required_final_tool_succeeded"] is True
    # The reserved edit turn is about which *tools* are offered, not about buying a
    # stronger model: this loop made progress every iteration, so it never escalates.
    assert call.call_args_list[1].kwargs["model"] == DEFAULT_RESEARCH_MODEL
    prep_tool_names = {tool["function"]["name"] for tool in call.call_args_list[1].kwargs["tools"]}
    assert prep_tool_names == {"set_sources", "finalize_roster"}
    assert call.call_args_list[2].kwargs["tool_choice"]["function"]["name"] == "finalize_roster"


@pytest.mark.asyncio
async def test_agent_loop_injects_actual_search_and_fetch_urls_into_editing_calls():
    source_url = "https://elections.example.gov/qualified-candidates"
    searched = _mock_openai_response(
        tool_calls=[{"id": "search", "function": {"name": "web_search", "arguments": json.dumps({"query": "roster"})}}]
    )
    fetched = _mock_openai_response(
        tool_calls=[{"id": "fetch", "function": {"name": "fetch_page", "arguments": json.dumps({"url": source_url})}}]
    )
    edited = _mock_openai_response(
        tool_calls=[{"id": "edit", "function": {"name": "set_sources", "arguments": json.dumps({"name": "Alice"})}}]
    )
    stopped = _mock_openai_response(content="Done")
    handler = MagicMock(return_value="OK")
    edit_tool = {
        "type": "function",
        "function": {"name": "set_sources", "description": "Set", "parameters": {"type": "object"}},
    }

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as call,
        patch(
            "pipeline_client.agent.llm._serper_search",
            new_callable=AsyncMock,
            return_value=[{"url": source_url, "title": "Official roster"}],
        ),
        patch("pipeline_client.agent.llm._fetch_page", new_callable=AsyncMock, return_value="Official roster " * 20),
    ):
        call.side_effect = [searched, fetched, edited, stopped]
        await _agent_loop(
            "system",
            "user",
            model=DEFAULT_RESEARCH_MODEL,
            phase_name="roster-provenance",
            max_iterations=5,
            tools_mode=True,
            extra_tools=[edit_tool],
            extra_tool_handlers={"set_sources": handler},
        )

    trace = handler.call_args.args[0]["_research_trace"]
    assert trace["researched_urls"] == [source_url]
    assert trace["fetched_urls"] == [source_url]


@pytest.mark.asyncio
async def test_agent_loop_records_successful_election_lookup_as_fetched_provenance():
    source_url = "https://ballotpedia.org/Alabama%27s_2nd_Congressional_District_election,_2026"
    looked_up = _mock_openai_response(
        tool_calls=[
            {
                "id": "lookup",
                "function": {
                    "name": "ballotpedia_election_lookup",
                    "arguments": json.dumps({"race_id": "al-house-02-2026"}),
                },
            }
        ]
    )
    edited = _mock_openai_response(
        tool_calls=[{"id": "edit", "function": {"name": "set_sources", "arguments": json.dumps({"name": "Alice"})}}]
    )
    stopped = _mock_openai_response(content="Done")
    handler = MagicMock(return_value="OK")
    edit_tool = {
        "type": "function",
        "function": {"name": "set_sources", "description": "Set", "parameters": {"type": "object"}},
    }

    with (
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as call,
        patch(
            "pipeline_client.agent.llm._ballotpedia_election_lookup",
            new_callable=AsyncMock,
            return_value={
                "found": True,
                "page_url": source_url,
                "candidates": [{"name": "Shomari Figures"}, {"name": "Rhett Marques"}],
            },
        ),
    ):
        call.side_effect = [looked_up, edited, stopped]
        await _agent_loop(
            "system",
            "user",
            model=DEFAULT_RESEARCH_MODEL,
            phase_name="roster-lookup-provenance",
            max_iterations=4,
            tools_mode=True,
            extra_tools=[edit_tool],
            extra_tool_handlers={"set_sources": handler},
        )

    trace = handler.call_args.args[0]["_research_trace"]
    assert trace["researched_urls"] == [source_url]
    assert trace["fetched_urls"] == [source_url]


@pytest.mark.asyncio
async def test_agent_loop_escalates_after_repeated_blocked_edits():
    blocked_calls = _mock_openai_response(
        tool_calls=[
            {"id": "call_1", "function": {"name": "add_candidate", "arguments": json.dumps({"name": "A"})}},
            {"id": "call_2", "function": {"name": "add_candidate", "arguments": json.dumps({"name": "B"})}},
        ]
    )
    finished = _mock_openai_response(content="Roster left unchanged.")
    tool = {
        "type": "function",
        "function": {"name": "add_candidate", "description": "Add", "parameters": {"type": "object"}},
    }

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as call:
        call.side_effect = [blocked_calls, finished]
        await _agent_loop(
            "system",
            "user",
            model=SMALL_MODEL,
            phase_name="roster-test",
            tools_mode=True,
            extra_tools=[tool],
            extra_tool_handlers={"add_candidate": lambda _args: "Blocked adding candidate: insufficient evidence"},
            escalate_on_tool_errors=True,
        )

    assert [entry.kwargs["model"] for entry in call.call_args_list] == [SMALL_MODEL, escalation_for(SMALL_MODEL)]
    second_messages = call.call_args_list[1].args[0]
    assert any("pivot to higher-priority official evidence" in (message.get("content") or "") for message in second_messages)


@pytest.mark.asyncio
async def test_agent_loop_aborts_third_identical_blocked_required_final_tool_after_escalation():
    blocked = _mock_openai_response(
        tool_calls=[
            {
                "id": "finalize",
                "function": {"name": "finalize_roster", "arguments": json.dumps({"summary": "Official list"})},
            }
        ]
    )
    final_tool = {
        "type": "function",
        "function": {"name": "finalize_roster", "description": "Finalize", "parameters": {"type": "object"}},
    }

    with patch(
        "pipeline_client.agent.llm._call_openrouter",
        new_callable=AsyncMock,
        side_effect=[blocked, blocked, blocked],
    ) as call:
        with pytest.raises(RuntimeError, match="3 identical blocked finalize_roster calls"):
            await _agent_loop(
                "system",
                "user",
                model=SMALL_MODEL,
                phase_name="roster-repeat-blocked",
                max_iterations=8,
                tools_mode=True,
                extra_tools=[final_tool],
                extra_tool_handlers={
                    "finalize_roster": lambda _args: (
                        "ERROR: roster finalization blocked. Lock the exact office and contest stage "
                        "with set_race_identity."
                    )
                },
                required_final_tool_name="finalize_roster",
                escalate_on_tool_errors=True,
                return_tool_trace=True,
            )

    assert call.call_count == 3
    assert [entry.kwargs["model"] for entry in call.call_args_list] == [
        SMALL_MODEL,
        SMALL_MODEL,
        escalation_for(SMALL_MODEL),
    ]


@pytest.mark.asyncio
async def test_agent_loop_exposes_prerequisite_tools_after_forced_finalization_is_blocked():
    blocked_finalize = _mock_openai_response(
        tool_calls=[
            {
                "id": "blocked-finalize",
                "function": {"name": "finalize_roster", "arguments": json.dumps({"summary": "Official list"})},
            }
        ]
    )
    recovered = _mock_openai_response(
        tool_calls=[
            {
                "id": "identity",
                "function": {
                    "name": "set_race_identity",
                    "arguments": json.dumps({"office": "U.S. House", "contest_stage": "general"}),
                },
            },
            {
                "id": "finalize",
                "function": {"name": "finalize_roster", "arguments": json.dumps({"summary": "Official list"})},
            },
        ]
    )
    identity_locked = False

    def set_identity(_args):
        nonlocal identity_locked
        identity_locked = True
        return "OK"

    def finalize(_args):
        return "OK" if identity_locked else "ERROR: call set_race_identity first"

    tools = [
        {
            "type": "function",
            "function": {"name": "set_race_identity", "description": "Lock identity", "parameters": {"type": "object"}},
        },
        {
            "type": "function",
            "function": {"name": "finalize_roster", "description": "Finalize", "parameters": {"type": "object"}},
        },
    ]

    with (
        patch("pipeline_client.agent.llm.total_token_budget_reached", return_value=True),
        patch(
            "pipeline_client.agent.llm._call_openrouter",
            new_callable=AsyncMock,
            side_effect=[blocked_finalize, recovered],
        ) as call,
    ):
        result = await _agent_loop(
            "system",
            "user",
            model=SMALL_MODEL,
            phase_name="roster-prerequisite-recovery",
            max_iterations=5,
            tools_mode=True,
            extra_tools=tools,
            extra_tool_handlers={"set_race_identity": set_identity, "finalize_roster": finalize},
            required_final_tool_name="finalize_roster",
            return_tool_trace=True,
        )

    assert call.call_count == 2
    assert call.call_args_list[0].kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "finalize_roster"},
    }
    assert call.call_args_list[1].kwargs["tool_choice"] is None
    assert {tool["function"]["name"] for tool in call.call_args_list[1].kwargs["tools"]} == {
        "set_race_identity",
        "finalize_roster",
    }
    assert result["_tool_trace"]["required_final_tool_succeeded"] is True


@pytest.mark.asyncio
async def test_agent_loop_never_escalates_a_long_but_healthy_loop():
    """A loop that runs to its ceiling is thorough, not stalled.

    Escalating on loop position billed 46 upgrades against zero distress signals
    in one 90-minute window, at frontier rates on the run's largest prompts —
    roughly 65% of discovery's per-race cost. Once the token budget trips,
    ``force_final_tool`` is true on *every* remaining iteration, so an unlatched
    escalation re-fires each turn.
    """
    searching = _mock_openai_response(
        tool_calls=[{"id": "s", "function": {"name": "web_search", "arguments": json.dumps({"query": "roster"})}}]
    )
    finalized = _mock_openai_response(
        tool_calls=[{"id": "f", "function": {"name": "finalize_roster", "arguments": json.dumps({"summary": "ok"})}}]
    )
    final_tool = {
        "type": "function",
        "function": {"name": "finalize_roster", "description": "Finalize", "parameters": {"type": "object"}},
    }

    with (
        patch("pipeline_client.agent.llm.total_token_budget_reached", return_value=True),
        patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as call,
        patch("pipeline_client.agent.llm._serper_search", new_callable=AsyncMock, return_value=[]),
    ):
        call.side_effect = [searching, searching, finalized]
        await _agent_loop(
            "system",
            "user",
            model=DEFAULT_RESEARCH_MODEL,
            phase_name="roster-healthy",
            max_iterations=6,
            tools_mode=True,
            extra_tools=[final_tool],
            extra_tool_handlers={"finalize_roster": lambda _args: "OK"},
            required_final_tool_name="finalize_roster",
            escalate_on_tool_errors=True,
        )

    models = [entry.kwargs["model"] for entry in call.call_args_list]
    assert models == [DEFAULT_RESEARCH_MODEL] * len(models)
    assert escalation_for(DEFAULT_RESEARCH_MODEL) not in models


def test_tool_result_error_detection_handles_handler_blocking_conventions():
    from pipeline_client.agent.llm import _tool_result_is_error

    assert _tool_result_is_error("ERROR: missing evidence")
    assert _tool_result_is_error("Blocked adding candidate")
    assert _tool_result_is_error("Failed to update roster")
    assert not _tool_result_is_error("Added candidate")


@pytest.mark.asyncio
async def test_agent_loop_propagates_policy_violation_runtime_error():
    with patch(
        "pipeline_client.agent.llm._call_openrouter",
        new_callable=AsyncMock,
        side_effect=RuntimeError("OpenRouter rejected the simplified prompt due to content policy violation"),
    ):
        with pytest.raises(RuntimeError, match="policy"):
            await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")


@pytest.mark.asyncio
async def test_agent_loop_raises_on_empty_choices_response():
    empty_response = MagicMock()
    empty_response.choices = []

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock, return_value=empty_response):
        with pytest.raises(RuntimeError, match="empty or invalid response"):
            await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")


@pytest.mark.asyncio
async def test_agent_loop_elevates_model_on_bad_json():
    """A JSON-parse failure retries on the escalation target, not the same model."""

    bad_response = _mock_openai_response(content="not valid JSON")
    good_response = _mock_openai_response(content=json.dumps({"success": True}))

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_response, good_response]
        result = await _agent_loop(
            "system",
            "user",
            model=DEFAULT_RESEARCH_MODEL,
            phase_name="test-elevation",
        )

    assert result == {"success": True}
    assert mock_call.call_count == 2
    assert mock_call.call_args_list[0].kwargs["model"] == DEFAULT_RESEARCH_MODEL
    assert mock_call.call_args_list[1].kwargs["model"] == escalation_for(DEFAULT_RESEARCH_MODEL)


@pytest.mark.asyncio
async def test_agent_loop_recovers_from_truncated_tool_arguments():
    """Malformed tool-call arguments return a tool error instead of killing the phase."""

    truncated = '{"winner": "Jane Doe", "rationale": "Leads every published poll'
    bad_call = _mock_openai_response(
        tool_calls=[{"id": "call_1", "function": {"name": "set_forecast", "arguments": truncated}}],
    )
    good_call = _mock_openai_response(
        tool_calls=[
            {
                "id": "call_2",
                "function": {"name": "set_forecast", "arguments": json.dumps({"winner": "Jane Doe"})},
            }
        ],
    )
    done = _mock_openai_response(content="Done.")

    handler_calls = []

    def fake_handler(args):
        handler_calls.append(args)
        return "OK"

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
        mock.side_effect = [bad_call, good_call, done]
        result = await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test-forecast",
            tools_mode=True,
            extra_tools=[{"type": "function", "function": {"name": "set_forecast", "parameters": {}}}],
            extra_tool_handlers={"set_forecast": fake_handler},
        )

    assert result == {}
    # The truncated call never reached the handler; the retried call did.
    assert len(handler_calls) == 1
    assert handler_calls[0]["winner"] == "Jane Doe"

    sent_messages = mock.call_args_list[1].args[0]
    tool_replies = [m for m in sent_messages if m.get("role") == "tool"]
    assert tool_replies, "the malformed call must be answered so the conversation stays valid"
    assert "not valid JSON" in tool_replies[-1]["content"]


@pytest.mark.asyncio
async def test_agent_loop_treats_blank_tool_arguments_as_empty_object():
    """Models emit "" for no-argument tools; that is not a parse failure."""

    call = _mock_openai_response(
        tool_calls=[{"id": "call_1", "function": {"name": "read_profile", "arguments": ""}}],
    )
    done = _mock_openai_response(content="Done.")

    seen = []

    with patch("pipeline_client.agent.llm._call_openrouter", new_callable=AsyncMock) as mock:
        mock.side_effect = [call, done]
        await _agent_loop(
            "system",
            "user",
            model="gpt-5.4-mini",
            phase_name="test-blank-args",
            tools_mode=True,
            extra_tools=[{"type": "function", "function": {"name": "read_profile", "parameters": {}}}],
            extra_tool_handlers={"read_profile": lambda args: seen.append(args) or "profile"},
        )

    assert len(seen) == 1


def test_parse_tool_arguments_rejects_non_object_payloads():
    from pipeline_client.agent.llm import _parse_tool_arguments

    assert _parse_tool_arguments(None) == {}
    assert _parse_tool_arguments("   ") == {}
    assert _parse_tool_arguments('{"a": 1}') == {"a": 1}
    with pytest.raises(ValueError):
        _parse_tool_arguments("[1, 2]")
    with pytest.raises(ValueError):
        _parse_tool_arguments('{"a": ')
