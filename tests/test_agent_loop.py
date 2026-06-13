"""Tests for the _agent_loop function (direct answers, tool calls, retries, tools mode)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError

from pipeline_client.agent.agent import _agent_loop
from pipeline_client.agent.llm import _call_openai, _provider_usage_cost

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


# ---------------------------------------------------------------------------
# Standard mode tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_openai_retries_connection_error():
    """_call_openai retries transient SDK connection failures."""
    response = _mock_openai_response(content=json.dumps({"result": "ok"}))
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")),
            response,
        ]
    )

    with (
        patch("pipeline_client.agent.llm._get_openai_client", return_value=client),
        patch("pipeline_client.agent.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _call_openai(
            [{"role": "user", "content": "Return JSON."}],
            model="gpt-5.4-mini",
            max_retries=2,
        )

    assert result is response
    assert client.chat.completions.create.call_count == 2
    mock_sleep.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_agent_loop_produces_json():
    """_agent_loop returns parsed JSON when model gives a direct answer."""
    response = _mock_openai_response(content=json.dumps({"result": "ok"}))
    with patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock:
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
        patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock_call,
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
        patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock_call,
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

    with patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock:
        mock.side_effect = [bad, good]
        result = await _agent_loop("system", "user", model="gpt-5.4-mini", phase_name="test")

    assert result == {"ok": True}
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_raises_on_max_iterations():
    """_agent_loop raises RuntimeError when max iterations reached."""
    bad = _mock_openai_response(content="still not json")

    with patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock:
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
        patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock_call,
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
    with patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock:
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

    with patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock:
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
async def test_agent_loop_elevates_model_on_bad_json():
    """_agent_loop elevates model from cheap model to default model on retry when JSON parsing fails."""
    from pipeline_client.agent.model_registry import DEEPSEEK_FLASH_MODEL, NEMOTRON_ULTRA_MODEL

    bad_response = _mock_openai_response(content="not valid JSON")
    good_response = _mock_openai_response(content=json.dumps({"success": True}))

    with patch("pipeline_client.agent.llm._call_openai", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_response, good_response]
        result = await _agent_loop(
            "system",
            "user",
            model=DEEPSEEK_FLASH_MODEL,
            phase_name="test-elevation",
        )

    assert result == {"success": True}
    assert mock_call.call_count == 2
    assert mock_call.call_args_list[0].kwargs["model"] == DEEPSEEK_FLASH_MODEL
    assert mock_call.call_args_list[1].kwargs["model"] == NEMOTRON_ULTRA_MODEL
