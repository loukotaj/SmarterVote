"""Tests for shared models and multi-LLM review functionality."""

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest


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
        reviewed_at=datetime(2024, 1, 1),
        verdict="approved",
        score=100,
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


def test_poll_matchup_coerces_null_percentages():
    """Legacy/generated poll data can omit percentages without breaking validation."""
    from shared.models import PollMatchup

    matchup = PollMatchup.model_validate({"candidates": ["Alice", "Bob"], "percentages": None})

    assert matchup.percentages == []


def test_validation_grade_caps_error_flags_below_passing():
    """A high numeric average should not pass while error-severity review flags remain."""
    from pipeline_client.agent.review import compute_validation_grade

    grade = compute_validation_grade(
        [
            {"verdict": "approved", "score": 95, "flags": []},
            {
                "verdict": "flagged",
                "score": 91,
                "flags": [{"field": "candidates[0].name", "severity": "error", "concern": "Placeholder name"}],
            },
        ]
    )

    assert grade is not None
    assert grade["score"] == 79
    assert grade["grade"] == "C"
    assert grade["passed"] is False


# ---------------------------------------------------------------------------
# Review provider tests
# ---------------------------------------------------------------------------


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
