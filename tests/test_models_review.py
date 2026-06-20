"""Tests for shared models and multi-LLM review functionality."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest


def _valid_review_profile():
    from shared.models import CanonicalIssue

    return {
        "schema_version": "0.3",
        "id": "test-race-2026",
        "election_date": "2026-11-03",
        "updated_utc": "2026-06-14T00:00:00Z",
        "title": "2026 Test Governor Election",
        "description": (
            "Voters will elect a governor in the November 2026 general election. The contest includes candidates "
            "from the major parties and will determine control of the executive branch. Campaign debate has focused "
            "on public services, economic policy, and state administration."
        ),
        "candidates": [
            {
                "name": "Alice Example",
                "issues": {
                    issue.value: {
                        "issue": issue.value,
                        "stance": "No public position found",
                        "confidence": "low",
                        "sources": [],
                    }
                    for issue in CanonicalIssue
                },
            }
        ],
    }


def test_shared_models_have_new_fields():
    """shared/models.py has CareerEntry, EducationEntry, CandidateLink, AgentReview."""
    from shared.models import (
        AgentReview,
        Candidate,
        CandidateLink,
        CareerEntry,
        EducationEntry,
        RaceForecast,
        RaceJSON,
        ReviewFlag,
    )

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

    forecast = RaceForecast(
        predicted_winner_name="Alice Example",
        predicted_winner_party="Democratic",
        win_probability=0.68,
        party_probabilities={"Democratic": 0.68, "Republican": 0.32},
        margin_estimate=3.2,
        rating="lean_d",
        confidence="medium",
        rationale="Available polling and incumbency favor Alice.",
        based_on_poll_count=2,
        generated_at=datetime(2026, 6, 20),
        model="openai/gpt-5.4",
        source_urls=["https://example.com/poll"],
    )
    assert forecast.rating == "lean_d"
    assert forecast.party_probabilities["Democratic"] == 0.68

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
async def test_run_single_review_records_provider_metrics():
    from pipeline_client.agent.review import _run_single_review

    metrics = {}
    response = json.dumps({"verdict": "approved", "summary": "Complete review.", "flags": []})
    usage = {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "provider_cost_usd": 0.004,
        "estimated_cost_usd": 0.005,
    }

    with patch("pipeline_client.agent.review._call_review_model", new_callable=AsyncMock, return_value=(response, usage)):
        await _run_single_review("test-2026", "{}", provider="claude", metrics_sink=metrics)

    assert metrics["calls"] == 1
    assert metrics["providers"]["claude"]["prompt_tokens"] == 1200
    assert metrics["providers"]["claude"]["completion_tokens"] == 300
    assert metrics["providers"]["claude"]["provider_cost_usd"] == pytest.approx(0.004)


def test_semantic_review_packet_includes_every_modeled_profile_field():
    from pipeline_client.agent.review import build_semantic_review_packet, validate_semantic_review_packet
    from shared.models import Candidate, RaceJSON

    candidate = {field: f"candidate:{field}" for field in Candidate.model_fields}
    race = {field: f"race:{field}" for field in RaceJSON.model_fields}
    race["candidates"] = [candidate]
    race["reviews"] = [{"should": "not appear"}]
    race["validation_grade"] = {"should": "not appear"}
    race["generator"] = ["should-not-appear"]
    race["pipeline_state"] = {"complete": True}
    race["agent_metrics"] = {"tokens": 1}

    packet = build_semantic_review_packet(race)
    validate_semantic_review_packet(race, packet)

    assert set(packet) == set(RaceJSON.model_fields) - {
        "agent_metrics",
        "candidate_limit_note",
        "generator",
        "pipeline_state",
        "post_run_analysis",
        "reviews",
        "validation_grade",
    }
    assert set(packet["candidates"][0]) == set(Candidate.model_fields)
    assert packet["candidates"][0] == candidate


def test_review_change_manifest_reports_changed_paths_without_reducing_packet():
    from pipeline_client.agent.review import build_review_change_manifest

    previous = {"title": "Old", "candidates": [{"name": "Alice", "summary": "Before"}]}
    current = {"title": "New", "candidates": [{"name": "Alice", "summary": "After"}]}

    manifest = build_review_change_manifest(previous, current)

    assert "- title" in manifest
    assert "- candidates[0].summary" in manifest


@pytest.mark.asyncio
async def test_run_reviews_sends_identical_complete_packet_to_all_default_providers(monkeypatch):
    from pipeline_client.agent.review import run_reviews
    from shared.models import Candidate

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    profile = _valid_review_profile()
    received = []

    async def capture_review(_race_id, profile_json, *, provider, change_manifest, **_kwargs):
        received.append((provider, profile_json, change_manifest))
        return {"model": provider, "verdict": "approved", "flags": [], "summary": ""}

    with (
        patch("pipeline_client.agent.review._run_single_review", side_effect=capture_review),
        patch("pipeline_client.agent.review.check_profile_links", new_callable=AsyncMock, return_value=None),
    ):
        await run_reviews("test-race-2026", profile, change_manifest="Changed: title")

    assert {provider for provider, _, _ in received} == {"claude", "gemini", "grok"}
    assert len({payload for _, payload, _ in received}) == 1
    packet = json.loads(received[0][1])
    assert packet["candidates"][0]["name"] == profile["candidates"][0]["name"]
    assert packet["candidates"][0]["issues"] == profile["candidates"][0]["issues"]
    assert set(packet["candidates"][0]) == set(Candidate.model_fields)
    assert all(manifest == "Changed: title" for _, _, manifest in received)


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


def test_profile_quality_flags_title_like_description():
    from pipeline_client.agent.review import check_profile_quality

    result = check_profile_quality(
        {
            "title": "2026 United States Senate election in Arkansas",
            "description": "2026 United States Senate election in Arkansas",
        }
    )

    assert result["verdict"] == "flagged"
    description_flags = [flag for flag in result["flags"] if flag["field"] == "description"]
    assert description_flags[0]["severity"] == "error"


def test_profile_quality_accepts_substantive_description():
    from pipeline_client.agent.review import check_profile_quality

    result = check_profile_quality(_valid_review_profile())

    assert result["verdict"] == "approved"


def test_profile_quality_flags_duplicate_stale_and_unsourced_claims():
    from pipeline_client.agent.review import check_profile_quality

    profile = _valid_review_profile()
    candidate = profile["candidates"][0]
    candidate["summary"] = "Alice Example has served in public office."
    candidate["summary_sources"] = [
        {
            "url": "https://example.com/profile",
            "type": "government",
            "last_accessed": "2024-01-01T00:00:00Z",
        },
        {
            "url": "https://example.com/profile",
            "type": "government",
            "last_accessed": "2024-01-01T00:00:00Z",
        },
    ]
    candidate["issues"]["Healthcare"]["stance"] = "Supports expanding rural clinics."

    result = check_profile_quality(profile)
    concerns = [flag["concern"] for flag in result["flags"]]

    assert any("Duplicate source URL" in concern for concern in concerns)
    assert any("more than one year old" in concern for concern in concerns)
    assert any("Substantive issue stance has no supporting sources" in concern for concern in concerns)
