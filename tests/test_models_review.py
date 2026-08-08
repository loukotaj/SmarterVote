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
        "pipeline_state": {
            "issue_attempts": {f"issues:Alice Example:{issue.value}": 1 for issue in CanonicalIssue},
            "issue_research": {
                f"issues:Alice Example:{issue.value}": {
                    "status": "completed",
                    "attempts": 1,
                    "search_calls": 2,
                    "page_fetches": 0,
                }
                for issue in CanonicalIssue
            },
        },
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
        market_signals=[
            {
                "provider": "kalshi",
                "market_ticker": "KXTEST-26-DEM",
                "title": "Will a Democrat win the test race?",
                "matched_to": "Democratic",
                "matched_party": "Democratic",
                "implied_probability": 0.66,
                "yes_bid": 0.64,
                "yes_ask": 0.68,
                "as_of": "2026-06-23T12:00:00Z",
                "confidence": "medium",
            }
        ],
    )
    assert forecast.rating == "lean_d"
    assert forecast.party_probabilities["Democratic"] == 0.68
    assert forecast.market_signals[0].market_ticker == "KXTEST-26-DEM"

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


def test_race_identity_and_roster_provenance_fields_validate():
    from shared.models import ContestStage, RaceJSON

    race = RaceJSON.model_validate(
        {
            "id": "ga-governor-2026",
            "election_date": "2026-11-03",
            "updated_utc": "2026-06-29T00:00:00Z",
            "contest_stage": "post_primary_general",
            "candidates": [
                {
                    "name": "Alice",
                    "party": "Democratic",
                    "incumbent": False,
                    "roster_sources": [
                        {
                            "url": "https://example.gov/candidates",
                            "type": "official",
                            "title": "Certified candidate list",
                            "evidence": "Alice is listed as a nominee.",
                            "last_accessed": "2026-06-29T00:00:00Z",
                            "published_at": "2026-06-20T00:00:00Z",
                            "race_id": "ga-governor-2026",
                            "evidence_tier": 1,
                            "retrieval_status": "content",
                        }
                    ],
                }
            ],
            "pipeline_state": {
                "complete": True,
                "race_identity": {
                    "office": "Governor",
                    "state": "Georgia",
                    "contest_stage": "post_primary_general",
                    "official_roster_source_url": "https://example.gov/candidates",
                },
            },
        }
    )

    assert race.contest_stage == ContestStage.POST_PRIMARY_GENERAL
    assert race.pipeline_state.race_identity.contest_stage == ContestStage.POST_PRIMARY_GENERAL
    assert race.candidates[0].roster_sources[0].type == "official"
    assert race.candidates[0].roster_sources[0].race_id == "ga-governor-2026"
    assert race.candidates[0].roster_sources[0].evidence_tier == 1


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
    from pipeline_client.agent.review import _review_model_for, _run_single_review

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
    assert result["model"] == _review_model_for("claude", cheap_mode=False)


@pytest.mark.asyncio
async def test_run_single_review_gemini():
    """_run_single_review with the Gemini role returns structured review."""
    from pipeline_client.agent.review import _review_model_for, _run_single_review

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
        "run_audit",
        "validation_grade",
    }
    assert set(packet["candidates"][0]) == set(Candidate.model_fields)
    assert packet["candidates"][0] == candidate


def test_pipeline_state_preserves_durable_retry_failure_and_cleanup_fields():
    from shared.models import PipelineState

    state = PipelineState.model_validate(
        {
            "complete": False,
            "issue_attempts": {"issues:Alice:Economy": 2},
            "step_failures": [{"step": "forecast", "reason": "step_no_data", "detail": "missing source"}],
            "deterministic_cleanup": {"text_changes": 1},
        }
    ).model_dump(mode="json")

    assert state["issue_attempts"] == {"issues:Alice:Economy": 2}
    assert state["step_failures"][0]["step"] == "forecast"
    assert state["deterministic_cleanup"] == {"text_changes": 1}


def test_issue_research_effort_context_distinguishes_attempted_absence_from_omission():
    from pipeline_client.agent.review import build_issue_research_effort_context

    race = {
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Economy": {
                        "stance": "No public position found after repeated research attempts.",
                        "confidence": "low",
                        "sources": [],
                    }
                },
            }
        ],
        "pipeline_state": {
            "issue_attempts": {"issues:Alice:Economy": 2},
            "issue_research": {
                "issues:Alice:Economy": {
                    "status": "completed",
                    "attempts": 2,
                    "search_calls": 2,
                    "page_fetches": 1,
                }
            },
        },
    }

    context = build_issue_research_effort_context(race)

    assert "1/12 terminal issue outputs" in context
    assert "1/12 slots with recorded pipeline attempts (2 total attempts)" in context
    assert "1/12 slots with recorded search/fetch activity" in context
    assert "0 no-position outputs without sufficient research provenance" in context


def test_profile_quality_rejects_no_position_marker_without_attempt_provenance():
    from pipeline_client.agent.review import check_profile_quality
    from shared.models import CanonicalIssue

    race = {
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    issue.value: {
                        "stance": "No public position found after repeated research attempts.",
                        "confidence": "low",
                        "sources": [],
                    }
                    for issue in CanonicalIssue
                },
            }
        ],
        "pipeline_state": {"issue_attempts": {}},
    }

    review = check_profile_quality(race)

    provenance_flags = [flag for flag in review["flags"] if "completed audit" in flag["concern"]]
    assert len(provenance_flags) == 12
    assert all(flag["severity"] == "error" for flag in provenance_flags)


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
        # 400 is a real failure but not permanent, so it must not be auto-removed.
        assert await _verify_url(AsyncMock(), url) == ("HTTP error 400", False)


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


@pytest.mark.asyncio
async def test_verify_url_marks_unresolvable_host_permanent():
    """A host that does not resolve is at least as dead as a 404."""
    import httpx

    from pipeline_client.agent.review import _verify_url

    url = "https://www.ballotpedia.org/Joanne_Kuniansky"
    exc = httpx.ConnectError("[Errno -2] Name or service not known")

    with patch("pipeline_client.agent.review._get_validated", new_callable=AsyncMock, side_effect=exc):
        reason, permanent = await _verify_url(AsyncMock(), url)

    assert permanent is True
    assert "Name or service not known" in reason


@pytest.mark.asyncio
async def test_verify_url_keeps_timeouts_transient():
    import httpx

    from pipeline_client.agent.review import _verify_url

    with patch(
        "pipeline_client.agent.review._get_validated",
        new_callable=AsyncMock,
        side_effect=httpx.ReadTimeout("timed out"),
    ):
        _reason, permanent = await _verify_url(AsyncMock(), "https://example.com/slow")

    assert permanent is False


def test_dead_source_removal_covers_unresolvable_hosts():
    """Regression: a DNS-dead citation blocked publication across five runs."""
    from pipeline_client.agent.review import _remove_confirmed_dead_candidate_sources

    dead = "https://www.ballotpedia.org/Joanne_Kuniansky"
    race_json = {
        "candidates": [
            {
                "name": "Joanne Kuniansky",
                "issues": {
                    "Economy": {
                        "stance": "Supports a public works program.",
                        "sources": [{"url": dead}, {"url": "https://themilitant.com/2026/swp-campaign"}],
                    }
                },
            }
        ]
    }
    link_review = {
        "flags": [
            {
                "field": "candidates[0].issues.Economy.sources[0].url",
                "concern": f"Cited source URL ({dead}) returned a dead link: Request failed: [Errno -2] Name or service not known.",
                "permanent_failure": True,
            }
        ]
    }

    removed = _remove_confirmed_dead_candidate_sources(race_json, link_review)

    assert removed == 1
    remaining = [s["url"] for s in race_json["candidates"][0]["issues"]["Economy"]["sources"]]
    assert dead not in remaining
    assert "https://themilitant.com/2026/swp-campaign" in remaining


def test_dead_source_removal_leaves_transient_failures_alone():
    from pipeline_client.agent.review import _remove_confirmed_dead_candidate_sources

    url = "https://example.com/slow"
    race_json = {"candidates": [{"name": "A", "issues": {"Economy": {"stance": "x", "sources": [{"url": url}]}}}]}
    link_review = {
        "flags": [
            {
                "field": "candidates[0].issues.Economy.sources[0].url",
                "concern": f"Cited source URL ({url}) returned a dead link: Request failed: timed out.",
                "permanent_failure": False,
            }
        ]
    }

    assert _remove_confirmed_dead_candidate_sources(race_json, link_review) == 0


def test_stance_level_audit_survives_missing_pipeline_state():
    """Regression: audits stored only in pipeline_state vanished for candidates a
    later targeted run did not re-research, so review rejected their documented
    absences and no sequence of runs could converge."""
    from pipeline_client.agent.review import check_profile_quality

    profile = {
        "id": "nj-senate-2026",
        "candidates": [
            {
                "name": "Justin Murphy",
                "issues": {
                    "Tech & AI": {
                        "stance": "No public position found",
                        "confidence": "low",
                        "sources": [],
                        "research_audit": {
                            "status": "completed",
                            "attempts": 1,
                            "search_calls": 2,
                            "page_fetches": 1,
                        },
                    }
                },
            }
        ],
        # Deliberately empty: this run researched somebody else.
        "pipeline_state": {"issue_attempts": {}, "issue_research": {}},
    }

    result = check_profile_quality(profile)
    audit_flags = [f for f in result.get("flags", []) if "completed audit" in str(f.get("concern", ""))]

    assert audit_flags == []


def test_unaudited_absence_is_still_flagged():
    """The guard must still catch an absence nothing ever researched."""
    from pipeline_client.agent.review import check_profile_quality

    profile = {
        "id": "nj-senate-2026",
        "candidates": [
            {
                "name": "Justin Murphy",
                "issues": {
                    "Tech & AI": {"stance": "No public position found", "confidence": "low", "sources": []},
                },
            }
        ],
        "pipeline_state": {"issue_attempts": {}, "issue_research": {}},
    }

    result = check_profile_quality(profile)
    audit_flags = [f for f in result.get("flags", []) if "completed audit" in str(f.get("concern", ""))]

    assert len(audit_flags) == 1


def test_research_audit_survives_schema_roundtrip():
    """An undeclared field would be stripped by RaceJSON validation."""
    from shared.models import IssueStance

    stance = IssueStance.model_validate(
        {
            "stance": "No public position found",
            "confidence": "low",
            "sources": [],
            "research_audit": {"status": "completed", "attempts": 1, "search_calls": 2, "page_fetches": 1},
        }
    )

    assert stance.research_audit is not None
    assert stance.model_dump()["research_audit"]["search_calls"] == 2


def test_dead_source_removal_handles_urls_containing_parentheses():
    """Ballotpedia/Wikipedia disambiguation URLs contain parentheses.

    Regression: the URL was recovered from the flag's prose with a regex that
    stopped at the first ')', producing a truncated address that never matched
    the stored citation, so those dead links could never be auto-removed.
    """
    from pipeline_client.agent.review import _remove_confirmed_dead_candidate_sources

    dead = "https://www.ballotpedia.org/Alabama%27s_2nd_Congressional_District_election,_2026_(August_11_Republican_primary)"
    race_json = {
        "candidates": [
            {
                "name": "David Matthews",
                "issues": {
                    "Election Policy": {
                        "stance": "Supports voter ID.",
                        "sources": [{"url": dead}, {"url": "https://al.com/politics/story"}],
                    }
                },
            }
        ]
    }
    link_review = {
        "flags": [
            {
                "field": "candidates[0].issues.Election Policy.sources[0].url",
                "concern": f"Cited source URL ({dead}) returned a dead link: Request failed: [Errno -2] Name or service not known.",
                "permanent_failure": True,
                "url": dead,
            }
        ]
    }

    assert _remove_confirmed_dead_candidate_sources(race_json, link_review) == 1
    remaining = [s["url"] for s in race_json["candidates"][0]["issues"]["Election Policy"]["sources"]]
    assert dead not in remaining
    assert "https://al.com/politics/story" in remaining


@pytest.mark.asyncio
async def test_verify_url_marks_tls_failure_permanent():
    """A host whose certificate will not validate is not a usable citation."""
    import httpx

    from pipeline_client.agent.review import _verify_url

    exc = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer")

    with patch("pipeline_client.agent.review._get_validated", new_callable=AsyncMock, side_effect=exc):
        _reason, permanent = await _verify_url(AsyncMock(), "https://www.sos.alabama.gov/doc.pdf")

    assert permanent is True


def test_missing_issues_does_not_fail_a_run_that_skipped_issue_research():
    """A lightweight refresh does not collect issue stances, so grading it on their
    absence measures the wrong thing. md-house-01-2026 was approved by 3/3
    reviewers at an average of 93 and still graded C, because the missing stances
    capped the score at 79 and blocked publication. The gap is still reported, as
    info, because the race does eventually need issue research."""
    from pipeline_client.agent.review import check_profile_quality, compute_validation_grade

    profile = _valid_review_profile()
    for candidate in profile["candidates"]:
        candidate["issues"] = {}

    scoped_out = check_profile_quality(profile, issues_step_ran=False)
    missing = [f for f in scoped_out["flags"] if f["field"].endswith(".issues")]
    assert missing, "the gap must still be reported"
    assert all(f["severity"] == "info" for f in missing)

    in_scope = check_profile_quality(profile, issues_step_ran=True)
    assert any(f["severity"] == "error" for f in in_scope["flags"] if f["field"].endswith(".issues"))

    approvals = [
        {"model": "anthropic/claude-haiku-4.5", "verdict": "approved", "score": 92, "flags": []},
        {"model": "google/gemini-3.1-flash-lite", "verdict": "approved", "score": 96, "flags": []},
        {"model": "x-ai/grok-4.3", "verdict": "approved", "score": 92, "flags": []},
    ]
    refreshed = compute_validation_grade(approvals + [scoped_out])
    assert refreshed["passed"] is True, refreshed["summary"]
    assert refreshed["grade"] in {"A", "B"}

    researched = compute_validation_grade(approvals + [in_scope])
    assert researched["passed"] is False
    assert researched["score"] == 79
