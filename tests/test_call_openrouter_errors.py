"""Behavioral tests for _call_openrouter's error-classification branches:
bad request / content-policy retry, rate limiting, and 5xx provider errors.

tests/test_agent_loop.py already covers the connection-error retry path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIStatusError, BadRequestError, RateLimitError

from pipeline_client.agent.errors import PermanentProviderError, RetryableProviderError
from pipeline_client.agent.llm import _call_openrouter


def _response(status_code: int, headers: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return httpx.Response(status_code, request=request, headers=headers or {})


def _mock_success_response(content="ok"):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, cost=None)
    return resp


# ---------------------------------------------------------------------------
# BadRequestError / content policy violation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_openrouter_non_policy_bad_request_raises_permanent_error_immediately():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=BadRequestError("model does not exist", response=_response(400), body=None)
    )

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(PermanentProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "hi"}],
                model="gpt-5.4-mini",
                max_retries=3,
            )

    assert raised.value.code == "bad_request"
    assert client.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_call_openrouter_policy_violation_retries_with_simplified_prompt_and_succeeds():
    client = MagicMock()
    success = _mock_success_response()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            BadRequestError("content policy violation detected", response=_response(400), body=None),
            success,
        ]
    )
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "u2"},
    ]

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        result = await _call_openrouter(messages, model="gpt-5.4-mini", max_retries=3)

    assert result is success
    assert client.chat.completions.create.call_count == 2
    # Second call must have used the simplified (shorter) message list.
    second_call_kwargs = client.chat.completions.create.call_args_list[1].kwargs
    assert len(second_call_kwargs["messages"]) == 3


@pytest.mark.asyncio
async def test_call_openrouter_policy_violation_persists_raises_permanent_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=BadRequestError("content policy violation detected", response=_response(400), body=None)
    )
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "u2"},
    ]

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(PermanentProviderError) as raised:
            await _call_openrouter(messages, model="gpt-5.4-mini", max_retries=3)

    assert raised.value.code == "policy_violation"
    assert client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_call_openrouter_policy_violation_too_short_to_simplify_raises_immediately():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=BadRequestError("content policy violation detected", response=_response(400), body=None)
    )
    # Only 2 messages: simplification keeps both (i < 2), so nothing shrinks.
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(PermanentProviderError) as raised:
            await _call_openrouter(messages, model="gpt-5.4-mini", max_retries=3)

    assert raised.value.code == "bad_request"
    assert client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# RateLimitError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_openrouter_rate_limit_exhausted_raises_retryable_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RateLimitError("rate limited", response=_response(429), body=None))

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(RetryableProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "hi"}],
                model="gpt-5.4-mini",
                max_retries=1,
            )

    assert raised.value.code == "rate_limited"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_call_openrouter_rate_limit_retries_using_retry_after_header():
    client = MagicMock()
    success = _mock_success_response()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            RateLimitError("rate limited", response=_response(429, {"retry-after": "5"}), body=None),
            success,
        ]
    )

    with (
        patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client),
        patch("pipeline_client.agent.llm.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _call_openrouter(
            [{"role": "user", "content": "hi"}],
            model="gpt-5.4-mini",
            max_retries=3,
        )

    assert result is success
    assert client.chat.completions.create.call_count == 2
    mock_sleep.assert_awaited_once()
    # retry-after=5 should be honored as (at least) the wait duration.
    assert mock_sleep.call_args.args[0] >= 5


@pytest.mark.asyncio
async def test_call_openrouter_rate_limit_without_retry_after_uses_backoff():
    client = MagicMock()
    success = _mock_success_response()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            RateLimitError("rate limited", response=_response(429), body=None),
            success,
        ]
    )

    with (
        patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client),
        patch("pipeline_client.agent.llm.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _call_openrouter(
            [{"role": "user", "content": "hi"}],
            model="gpt-5.4-mini",
            max_retries=3,
        )

    assert result is success
    mock_sleep.assert_awaited_once_with(30)


# ---------------------------------------------------------------------------
# APIStatusError (non-rate-limit HTTP errors)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_openrouter_client_error_status_raises_permanent_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=APIStatusError("teapot", response=_response(418), body=None))

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(PermanentProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "hi"}],
                model="gpt-5.4-mini",
                max_retries=3,
            )

    assert raised.value.code == "request_rejected"
    assert client.chat.completions.create.call_count == 1


@pytest.mark.parametrize("status_code", [401, 402, 403])
@pytest.mark.asyncio
async def test_call_openrouter_auth_statuses_are_classified_as_auth_failure(status_code):
    """402 belongs here as much as 401/403 do.

    On 2026-08-30 a zero OpenRouter balance returned 402 ("Payment Required")
    2,277 times in 18 minutes. Because 402 was missing from the auth tuple,
    every one of those runs was filed as `request_rejected` — indistinguishable
    from the agent sending a malformed prompt — so nothing upstream could tell
    "we're out of credit" apart from a genuine research failure.
    """
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=APIStatusError("no credit", response=_response(status_code), body=None)
    )

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(PermanentProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "hi"}],
                model="gpt-5.4-mini",
                max_retries=3,
            )

    assert raised.value.code == "auth_failure"
    assert client.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_call_openrouter_catalog_model_404_retries_then_succeeds():
    client = MagicMock()
    success = _mock_success_response()
    client.chat.completions.create = AsyncMock(
        side_effect=[APIStatusError("no endpoints", response=_response(404), body=None), success]
    )

    with (
        patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client),
        patch("pipeline_client.agent.llm.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _call_openrouter(
            [{"role": "user", "content": "hi"}],
            model="openai/gpt-5.6-sol",
            max_retries=3,
        )

    assert result is success
    assert client.chat.completions.create.call_count == 2
    mock_sleep.assert_awaited_once_with(2.0)


@pytest.mark.asyncio
async def test_call_openrouter_catalog_model_404_exhaustion_is_retryable():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=APIStatusError("no endpoints", response=_response(404), body=None))

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(RetryableProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "hi"}],
                model="openai/gpt-5.6-sol",
                max_retries=1,
            )

    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_call_openrouter_server_error_exhausted_raises_retryable_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=APIStatusError("server error", response=_response(503), body=None))

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(RetryableProviderError) as raised:
            await _call_openrouter(
                [{"role": "user", "content": "hi"}],
                model="gpt-5.4-mini",
                max_retries=1,
            )

    assert raised.value.code == "provider_unavailable"


@pytest.mark.asyncio
async def test_call_openrouter_server_error_retries_then_succeeds():
    client = MagicMock()
    success = _mock_success_response()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            APIStatusError("server error", response=_response(503), body=None),
            success,
        ]
    )

    with (
        patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client),
        patch("pipeline_client.agent.llm.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _call_openrouter(
            [{"role": "user", "content": "hi"}],
            model="gpt-5.4-mini",
            max_retries=3,
        )

    assert result is success
    mock_sleep.assert_awaited_once()
