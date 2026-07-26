"""Integration-level tests for run_agent's final run_health verdict.

Complements tests/test_run_health.py (which tests the taxonomy module in
isolation) by checking that run_agent actually wires per-step failures
recorded during phase execution into the final race_json["run_health"].
"""

from unittest.mock import AsyncMock, patch

import pytest

from pipeline_client.agent.agent import run_agent


@pytest.fixture(autouse=True)
def no_openrouter_key(monkeypatch):
    """Unit tests mock agent phases; never call real OpenRouter reviews."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_run_agent_reports_healthy_when_no_review_and_no_failures():
    """No candidates means no issues/finance work is attempted, so nothing can fail."""
    discovery_result = {"id": "healthy-2024", "candidates": []}
    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = discovery_result
        result = await run_agent(
            "healthy-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["run_health"]["status"] == "healthy"
    assert result["run_health"]["reasons"] == []
    assert result["run_health"]["step_failures"] == []


@pytest.mark.asyncio
async def test_run_agent_reports_degraded_when_steps_silently_produce_no_data():
    """Mirrors test_run_agent_fresh's mocked shape (see tests/test_run_agent.py):
    every issue sub-agent call returns an empty dict (no set_issue_stance tool
    call), which _research_issue_unit treats as a genuine failure — and the
    finance phase likewise gets an empty patch, leaving donor/voting summaries
    blank for the only candidate. Neither of these raises, so without run_health
    they would pass silently despite pipeline_state.complete staying True."""
    discovery_result = {"id": "degraded-2024", "candidates": [{"name": "Alice", "issues": {}}]}
    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
    ):
        mock_loop.return_value = {}
        mock_loop.side_effect = [discovery_result] + [{"image_url": None}] + [{}] * 15

        result = await run_agent(
            "degraded-2024",
            cheap_mode=True,
            enabled_steps=["discovery", "images", "issues", "finance", "refinement"],
        )

    assert result["run_health"]["status"] == "degraded"
    assert result["run_health"]["reasons"] == ["step_no_data"]
    step_names = {f["step"] for f in result["pipeline_state"]["step_failures"]}
    assert "issues" in step_names
    assert "finance" in step_names


@pytest.mark.asyncio
async def test_run_agent_registers_placeholder_content_for_literal_junk_stance():
    """A discovery response with a literal 'DRAFT' stance must register as a
    failure — not just silently get normalized to the generic missing marker."""
    discovery_result = {
        "id": "placeholder-2024",
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Economy": {"issue": "Economy", "stance": "DRAFT", "confidence": "low", "sources": []},
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
            "placeholder-2024",
            cheap_mode=True,
            enabled_steps=["discovery"],
        )

    stance = result["candidates"][0]["issues"]["Economy"]["stance"]
    assert stance == "No public position found after repeated research attempts."

    reasons = result["run_health"]["reasons"]
    assert "placeholder_content" in reasons
    detail = next(f["detail"] for f in result["pipeline_state"]["step_failures"] if f["reason"] == "placeholder_content")
    assert "DRAFT" in detail


@pytest.mark.asyncio
async def test_run_agent_reports_failed_when_review_ran_but_did_not_pass():
    """A run that goes through review with a failing grade must not be HEALTHY —
    that's exactly the "pipeline_state.complete but review actually failed" case
    from CLAUDE.md rule 7. Mirrors test_run_agent_respects_review_provider_selection's
    mocked shape (empty roster, discovery+review only) to keep the "issues" step out
    of the picture entirely."""
    discovery_result = {"id": "review-failed-2024", "candidates": []}
    failing_reviews = [
        {"model": "anthropic/claude-haiku-4.5", "verdict": "rejected", "score": 40, "summary": "Too thin", "flags": []},
    ]

    with (
        patch("pipeline_client.agent.phases._agent_loop", new_callable=AsyncMock) as mock_loop,
        patch("pipeline_client.agent.agent._load_existing", return_value=None),
        patch("pipeline_client.agent.agent.run_reviews", new_callable=AsyncMock) as mock_reviews,
    ):
        mock_loop.return_value = discovery_result
        mock_reviews.return_value = failing_reviews

        result = await run_agent(
            "review-failed-2024",
            cheap_mode=True,
            existing_data={},
            enabled_steps=["discovery", "review"],
            review_providers=["claude"],
        )

    assert result["validation_grade"]["passed"] is False
    assert result["run_health"]["status"] == "failed"
    assert "validation_failed" in result["run_health"]["reasons"]
