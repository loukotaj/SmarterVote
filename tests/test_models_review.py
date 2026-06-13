"""Tests for shared models and multi-LLM review functionality."""

import json
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
    assert c.donor_sources == []
    assert c.image_url is None

    finance_source = {
        "url": "https://www.fec.gov/data/candidate/H0EXAMPLE/",
        "type": "finance",
        "title": "FEC candidate profile",
        "last_accessed": "2026-05-16T00:00:00Z",
    }
    c_with_finance = Candidate(name="Finance Test", donor_sources=[finance_source])
    assert str(c_with_finance.donor_sources[0].url) == finance_source["url"]
    assert c_with_finance.donor_sources[0].type == "finance"

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
# Review role tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_single_review_claude():
    """_run_single_review with the Claude role returns structured review."""
    from pipeline_client.agent.review import DEFAULT_CLAUDE_MODEL, _run_single_review

    review_response = json.dumps(
        {
            "verdict": "approved",
            "summary": "Looks good.",
            "flags": [],
        }
    )

    with patch("pipeline_client.agent.review._call_review_model", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = review_response
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="claude")

    assert result is not None
    assert result["verdict"] == "approved"
    assert result["model"] == DEFAULT_CLAUDE_MODEL


@pytest.mark.asyncio
async def test_run_single_review_gemini():
    """_run_single_review with the Gemini role returns structured review."""
    from pipeline_client.agent.review import DEFAULT_GEMINI_MODEL, _run_single_review

    review_response = json.dumps(
        {
            "verdict": "flagged",
            "summary": "Found issues.",
            "flags": [{"field": "test", "concern": "bad", "severity": "warning"}],
        }
    )

    with patch("pipeline_client.agent.review._call_review_model", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = review_response
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="gemini")

    assert result is not None
    assert result["verdict"] == "flagged"
    assert len(result["flags"]) == 1


@pytest.mark.asyncio
async def test_run_single_review_handles_failure():
    """_run_single_review returns None on failure."""
    from pipeline_client.agent.review import _run_single_review

    with patch("pipeline_client.agent.review._call_review_model", new_callable=AsyncMock) as mock_claude:
        mock_claude.side_effect = RuntimeError("API down")
        result = await _run_single_review("test-2024", '{"id": "test"}', provider="claude")

    assert result is None


@pytest.mark.asyncio
async def test_check_profile_links():
    """check_profile_links programmatically detects dead and active URLs."""
    import httpx

    from pipeline_client.agent.review import check_profile_links

    # Mock the http responses for our URL checking
    mock_responses = {
        "https://example.com/active1": 200,
        "https://example.com/active2": 200,
        "https://example.com/dead": 404,
    }

    async def mock_head(url, *args, **kwargs):
        status = mock_responses.get(url, 404)
        return httpx.Response(status, request=httpx.Request("HEAD", url))

    race_data = {
        "id": "mo-senate-2026",
        "candidates": [
            {
                "name": "Candidate A",
                "summary_sources": [
                    {"url": "https://example.com/active1", "type": "website", "last_accessed": "2026-06-12T00:00:00Z"}
                ],
                "issues": {
                    "Healthcare": {
                        "stance": "Supports X",
                        "confidence": "high",
                        "sources": [
                            {"url": "https://example.com/active2", "type": "website", "last_accessed": "2026-06-12T00:00:00Z"},
                            {"url": "https://example.com/dead", "type": "news", "last_accessed": "2026-06-12T00:00:00Z"},
                        ],
                    }
                },
            }
        ],
    }

    # Patch AsyncClient methods to mock real HTTP calls
    with patch("httpx.AsyncClient.head", side_effect=mock_head), patch("httpx.AsyncClient.get", side_effect=mock_head):
        review_result = await check_profile_links(race_data)

    assert review_result["model"] == "automated-link-validator"
    assert review_result["verdict"] == "flagged"
    assert len(review_result["flags"]) == 1
    assert "https://example.com/dead" in review_result["flags"][0]["concern"]
    assert review_result["flags"][0]["field"] == "candidates[0].issues.Healthcare.sources[1].url"


@pytest.mark.asyncio
async def test_check_profile_links_skips_profiles_without_sources():
    from pipeline_client.agent.review import check_profile_links

    assert await check_profile_links({"candidates": []}) is None


@pytest.mark.asyncio
async def test_verify_url_treats_facebook_400_as_inconclusive():
    import httpx

    from pipeline_client.agent.review import _verify_url

    url = (
        "https://www.facebook.com/FredLoveforGovernor/posts/"
        "ive-noticed-some-of-you-saying-youre-not-familiar-with-my-platform-yet-and-i-hea/842216614978960/"
    )
    response = httpx.Response(400, request=httpx.Request("GET", url))

    with patch("pipeline_client.agent.review._get_validated", new_callable=AsyncMock, return_value=response):
        assert await _verify_url(AsyncMock(), url) is None


@pytest.mark.asyncio
async def test_verify_url_still_flags_non_facebook_400():
    import httpx

    from pipeline_client.agent.review import _verify_url

    url = "https://example.com/bad-request"
    response = httpx.Response(400, request=httpx.Request("GET", url))

    with patch("pipeline_client.agent.review._get_validated", new_callable=AsyncMock, return_value=response):
        assert await _verify_url(AsyncMock(), url) == "HTTP error 400"
