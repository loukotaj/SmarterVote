"""Tests for deadline-aware agent run budgets."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError

from pipeline_client.agent.llm import _call_openrouter
from pipeline_client.agent.run_budget import RunBudget, RunBudgetExceeded


def test_run_budget_bounds_timeout_and_sleep():
    now = [100.0]
    budget = RunBudget(deadline_at=130.0, checkpoint_buffer_seconds=5.0, clock=lambda: now[0])

    assert budget.remaining_seconds() == 30.0
    assert budget.can_start_call(25.0)
    assert not budget.can_start_call(26.0)
    assert budget.bounded_timeout(60.0) == 25.0
    assert budget.bounded_sleep(40.0) == 25.0


def test_run_budget_rejects_work_inside_checkpoint_buffer():
    budget = RunBudget(deadline_at=110.0, checkpoint_buffer_seconds=15.0, clock=lambda: 100.0)

    with pytest.raises(RunBudgetExceeded):
        budget.require_call_time(1.0, operation="test call")
    with pytest.raises(RunBudgetExceeded):
        budget.bounded_timeout(30.0, operation="test request")
    with pytest.raises(RunBudgetExceeded):
        budget.bounded_sleep(1.0, operation="test retry")


@pytest.mark.asyncio
async def test_openrouter_refuses_call_when_run_budget_is_exhausted():
    client = MagicMock()
    client.chat.completions.create = AsyncMock()
    budget = RunBudget(deadline_at=110.0, checkpoint_buffer_seconds=15.0, clock=lambda: 100.0)

    with patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client):
        with pytest.raises(RunBudgetExceeded):
            await _call_openrouter(
                [{"role": "user", "content": "Return JSON."}],
                model="openai/gpt-5.4-mini",
                run_budget=budget,
            )

    client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_openrouter_retry_stops_before_deadline():
    now = [100.0]
    budget = RunBudget(deadline_at=108.0, checkpoint_buffer_seconds=0.0, clock=lambda: now[0])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    )

    async def advance_clock(seconds):
        now[0] += seconds + 2.0

    with (
        patch("pipeline_client.agent.llm._get_openrouter_client", return_value=client),
        patch("pipeline_client.agent.llm.random.uniform", return_value=1.0),
        patch("pipeline_client.agent.llm.asyncio.sleep", new=AsyncMock(side_effect=advance_clock)),
    ):
        with pytest.raises(RunBudgetExceeded):
            await _call_openrouter(
                [{"role": "user", "content": "Return JSON."}],
                model="openai/gpt-5.4-mini",
                max_retries=3,
                run_budget=budget,
            )

    assert client.chat.completions.create.call_count == 1
