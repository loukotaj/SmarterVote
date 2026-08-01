"""Tests for editing tool handlers, roster sync, candidate targeting, and search cache."""

import json
import tempfile

import pytest

from pipeline_client.agent.agent import _select_target_candidates

# ---------------------------------------------------------------------------
# Candidate targeting
# ---------------------------------------------------------------------------


def test_select_target_candidates_case_insensitive():
    """Candidate targeting matches names case-insensitively and returns canonical names."""
    selected = _select_target_candidates(
        ["Tom Cotton", "Jeff Wadlin"],
        ["jeff wadlin"],
        log=lambda *_: None,
    )
    assert selected == ["Jeff Wadlin"]


# ---------------------------------------------------------------------------
# Editing tool schemas
# ---------------------------------------------------------------------------


def test_editing_tool_schemas_exist():
    """All editing tool schemas are importable from agent module."""
    from pipeline_client.agent.agent import (
        ADD_CANDIDATE_TOOL,
        ADD_LINK_TOOL,
        ADD_POLL_TOOL,
        CANDIDATE_TOOLS,
        FINALIZE_METADATA_TOOL,
        ISSUE_TOOLS,
        RACE_TOOLS,
        READ_PROFILE_TOOL,
        RECORD_TOOLS,
        REMOVE_CANDIDATE_TOOL,
        RENAME_CANDIDATE_TOOL,
        ROSTER_TOOLS,
        SET_CANDIDATE_FIELD_TOOL,
        SET_CANDIDATE_ROSTER_SOURCES_TOOL,
        SET_CANDIDATE_SUMMARY_TOOL,
        SET_DONOR_SUMMARY_TOOL,
        SET_FORECAST_TOOL,
        SET_ISSUE_STANCE_TOOL,
        SET_RACE_IDENTITY_TOOL,
        SET_VOTING_SUMMARY_TOOL,
        UPDATE_RACE_FIELD_TOOL,
    )

    assert len(ROSTER_TOOLS) == 6
    assert len(CANDIDATE_TOOLS) == 2
    assert len(ISSUE_TOOLS) == 1
    assert len(RECORD_TOOLS) == 4  # donor_summary, voting_summary, add_link, remove_candidate_source_url
    assert len(RACE_TOOLS) == 3
    assert SET_FORECAST_TOOL["function"]["name"] == "set_forecast"
    assert SET_CANDIDATE_ROSTER_SOURCES_TOOL["function"]["name"] == "set_candidate_roster_sources"
    assert SET_RACE_IDENTITY_TOOL["function"]["name"] == "set_race_identity"
    assert READ_PROFILE_TOOL["function"]["name"] == "read_profile"
    assert FINALIZE_METADATA_TOOL["function"]["name"] == "finalize_metadata"


# ---------------------------------------------------------------------------
# Editing handlers
# ---------------------------------------------------------------------------


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
        "set_candidate_roster_sources",
        "set_race_identity",
        "finalize_roster",
        "set_candidate_field",
        "set_candidate_summary",
        "finalize_metadata",
        "set_issue_stance",
        "set_donor_summary",
        "set_voting_summary",
        "add_candidate_link",
        "remove_candidate_source_url",
        "add_poll",
        "remove_poll",
        "update_race_field",
        "set_forecast",
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


def test_set_forecast_handler_updates_race_forecast():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "Democratic"}], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["set_forecast"](
        {
            "predicted_winner_name": "Alice",
            "predicted_winner_party": "Democratic",
            "win_probability": 0.72,
            "party_probabilities": {"Democratic": 0.72, "Republican": 0.28},
            "margin_estimate": 4.5,
            "rating": "lean_d",
            "confidence": "medium",
            "rationale": "Alice leads based on the available race profile.",
            "takeaway": "Alice is favored, but the race is still competitive.",
            "key_reasons": ["Democratic candidate has a polling lead.", "The race profile favors Alice."],
            "uncertainty": "Sparse polling keeps the forecast confidence at medium.",
            "based_on_poll_count": 1,
            "source_urls": ["https://example.com/poll"],
        }
    )

    assert result == "Updated race.forecast."
    assert race_json["forecast"]["rating"] == "lean_d"
    assert race_json["forecast"]["win_probability"] == 0.72
    assert race_json["forecast"]["takeaway"] == "Alice is favored, but the race is still competitive."
    assert race_json["forecast"]["key_reasons"] == [
        "Democratic candidate has a polling lead.",
        "The race profile favors Alice.",
    ]
    assert race_json["forecast"]["uncertainty"] == "Sparse polling keeps the forecast confidence at medium."
    assert race_json["forecast"]["generated_at"]


def test_set_forecast_derives_missing_win_probability_from_party_probability():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "Democratic"}], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["set_forecast"](
        {
            "predicted_winner_name": "Alice",
            "predicted_winner_party": "Democratic",
            "party_probabilities": {"Democratic": 0.64, "Republican": 0.36},
            "rating": "lean_d",
            "confidence": "medium",
            "rationale": "Alice has the stronger path.",
            "based_on_poll_count": 0,
            "source_urls": [],
        }
    )

    assert result == "Updated race.forecast."
    assert race_json["forecast"]["win_probability"] == 0.64


def test_set_forecast_derives_probability_when_predicted_party_has_party_suffix():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "Democratic"}], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["set_forecast"](
        {
            "predicted_winner_name": "Alice",
            "predicted_winner_party": "Democratic Party",
            "party_probabilities": {"Democratic": 0.72, "Republican": 0.28},
            "rating": "lean_d",
            "confidence": "medium",
            "rationale": "Alice is favored.",
        }
    )

    assert result == "Updated race.forecast."
    assert race_json["forecast"]["win_probability"] == 0.72


def test_set_forecast_rejects_winner_outside_active_roster():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "Democratic"}], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["set_forecast"](
        {
            "predicted_winner_name": "Historical Candidate",
            "predicted_winner_party": "Republican",
            "win_probability": 0.8,
            "rating": "likely_r",
            "confidence": "low",
            "rationale": "Invalid stale forecast.",
        }
    )

    assert result == "ERROR: Forecast winner 'Historical Candidate' is not in the active candidate roster."
    assert "forecast" not in race_json


def test_set_forecast_labels_tossup_when_no_winner_party_is_supplied():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["set_forecast"](
        {
            "party_probabilities": {"Democratic": 0.5, "Republican": 0.5},
            "rating": "tossup",
            "confidence": "low",
            "rationale": "The available evidence does not favor either party.",
            "based_on_poll_count": 0,
            "source_urls": [],
        }
    )

    assert result == "Updated race.forecast."
    assert race_json["forecast"]["predicted_winner_party"] == "Toss-up"


def test_set_forecast_derives_unique_leading_party_when_party_is_missing():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    handlers["set_forecast"](
        {
            "party_probabilities": {"Democratic": 0.58, "Republican": 0.42},
            "rating": "lean_d",
            "confidence": "medium",
            "rationale": "The available evidence gives Democrats a narrow edge.",
            "based_on_poll_count": 0,
            "source_urls": [],
        }
    )

    assert race_json["forecast"]["predicted_winner_party"] == "Democratic"


def test_add_candidate_link_ignores_legacy_string_links_for_dedup():
    """Legacy raw URL entries should not crash the editing handler."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "links": ["https://example.com/legacy"]}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["add_candidate_link"](
        {
            "candidate_name": "Alice",
            "url": "https://example.com/new",
            "title": "New Link",
            "type": "news",
        }
    )

    assert "Added" in result
    assert race_json["candidates"][0]["links"][-1] == {
        "url": "https://example.com/new",
        "title": "New Link",
        "type": "news",
    }


def test_set_donor_summary_accepts_structured_sources():
    """Finance citations should be stored separately from donor prose."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["set_donor_summary"](
        {
            "candidate_name": "Alice",
            "summary": "Alice raised $1.2M, mostly from individual donors.",
            "source_url": "https://www.fec.gov/data/candidate/H0ALICE/",
            "sources": [
                {
                    "url": "https://www.fec.gov/data/candidate/H0ALICE/",
                    "title": "FEC profile",
                    "type": "finance",
                },
                {
                    "url": "https://example.com/alice-fundraising",
                    "title": "Fundraising report",
                    "type": "news",
                },
            ],
        }
    )

    candidate = race_json["candidates"][0]
    assert "Updated donor summary" in result
    assert candidate["donor_summary"] == "Alice raised $1.2M, mostly from individual donors."
    assert candidate["donor_source_url"] == "https://www.fec.gov/data/candidate/H0ALICE/"
    assert [source["url"] for source in candidate["donor_sources"]] == [
        "https://www.fec.gov/data/candidate/H0ALICE/",
        "https://example.com/alice-fundraising",
    ]
    assert all(source["last_accessed"] for source in candidate["donor_sources"])


def test_editing_handlers_reject_webpage_image_and_normalize_sources():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "image_url": None, "issues": {}}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    image_result = handlers["set_candidate_field"](
        {
            "candidate_name": "Alice",
            "field": "image_url",
            "value": "https://example.com/candidate",
        }
    )
    handlers["set_candidate_summary"](
        {
            "candidate_name": "Alice",
            "summary": "Candidate summary.",
            "sources": [{"url": "https://ballotpedia.org/Alice", "type": "ballotpedia"}],
        }
    )
    handlers["set_issue_stance"](
        {
            "candidate_name": "Alice",
            "issue": "Healthcare",
            "stance": "Supports a stated policy.",
            "confidence": "high",
            "sources": [{"url": "https://example.com/issues"}],
        }
    )

    candidate = race_json["candidates"][0]
    assert image_result.startswith("ERROR:")
    assert candidate["image_url"] is None
    assert candidate["summary_sources"][0]["type"] == "website"
    assert candidate["summary_sources"][0]["last_accessed"]
    assert candidate["issues"]["Healthcare"]["sources"][0]["last_accessed"]


def test_add_candidate_handler():
    """add_candidate handler adds a candidate to race_json."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "ga-house-01-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["add_candidate"](
        {
            "name": "Alice Candidate",
            "party": "Democratic",
            "roster_sources": [
                {
                    "url": "https://sos.ga.gov/2026-candidates",
                    "type": "official",
                    "title": "2026 qualified candidates",
                    "evidence": "Alice Candidate filed for Georgia's 1st Congressional District in 2026.",
                    "published_at": "2026-03-10",
                    "race_id": "ga-house-01-2026",
                    "evidence_tier": 1,
                    "retrieval_status": "content",
                }
            ],
        }
    )
    assert "Added" in result
    assert len(race_json["candidates"]) == 1
    assert race_json["candidates"][0]["name"] == "Alice Candidate"
    assert race_json["candidates"][0]["roster_sources"][0]["evidence_tier"] == 1


def test_add_candidate_accepts_two_years_prior_evidence():
    """add_candidate accepts roster evidence published 2 years prior to the election year."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "ga-house-01-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["add_candidate"](
        {
            "name": "Alice Candidate",
            "party": "Democratic",
            "roster_sources": [
                {
                    "url": "https://sos.ga.gov/2024-candidates",
                    "type": "official",
                    "title": "2024 qualified candidates",
                    "evidence": "Alice Candidate filed for Georgia's 1st Congressional District in 2026.",
                    "published_at": "2024-11-15",
                    "race_id": "ga-house-01-2026",
                    "evidence_tier": 1,
                    "retrieval_status": "content",
                }
            ],
        }
    )
    assert "Added" in result
    assert len(race_json["candidates"]) == 1


def test_add_candidate_blocks_cross_race_contamination():
    """add_candidate blocks candidate already registered in another race in the same state."""
    from unittest.mock import patch

    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "ga-governor-2026", "state": "Georgia", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    # Mock _get_other_state_candidates to simulate "Jon Ossoff" is running for Senate
    with patch("pipeline_client.agent.handlers._get_other_state_candidates", return_value={"Jon Ossoff"}):
        result = handlers["add_candidate"](
            {
                "name": "Jon Ossoff",
                "party": "Democratic",
                "roster_sources": [
                    {
                        "url": "https://sos.ga.gov/2026-candidates",
                        "type": "official",
                        "title": "2026 qualified candidates",
                        "evidence": "Jon Ossoff filed in 2026.",
                        "published_at": "2026-03-10",
                        "race_id": "ga-governor-2026",
                        "evidence_tier": 1,
                        "retrieval_status": "content",
                    }
                ],
            }
        )

    assert "Blocked adding" in result
    assert "already registered as an active candidate in another race" in result
    assert len(race_json["candidates"]) == 0


def test_add_candidate_rejects_undated_or_generic_evidence():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "ga-house-01-2026", "candidates": [{"name": "Existing", "summary": "researched"}]}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    result = handlers["add_candidate"](
        {
            "name": "Alice Candidate",
            "party": "Democratic",
            "roster_sources": [
                {
                    "url": "https://example.com/alice",
                    "type": "news",
                    "title": "Alice Candidate biography",
                    "evidence": "Alice Candidate is active in politics.",
                    "race_id": "ga-house-01-2026",
                    "evidence_tier": 2,
                    "retrieval_status": "content",
                }
            ],
        }
    )

    assert "Blocked adding" in result
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Existing"]


def test_add_candidate_tier3_requires_independent_sources_unless_authoritative():
    from pipeline_client.agent.agent import _make_editing_handlers

    base_source = {
        "url": "https://localnews.example/blocked-page",
        "type": "news",
        "title": "Alice Candidate files for Georgia 1st District",
        "evidence": "Search result says Alice Candidate is running for Georgia's 1st Congressional District in 2026.",
        "published_at": "2026-03-10",
        "race_id": "ga-house-01-2026",
        "evidence_tier": 3,
        "retrieval_status": "snippet",
    }
    race_json = {"id": "ga-house-01-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    assert "Blocked adding" in handlers["add_candidate"](
        {"name": "Alice Candidate", "party": "Democratic", "roster_sources": [base_source]}
    )

    second_source = {
        **base_source,
        "url": "https://anothernews.example/alice-candidate",
        "title": "Georgia 1st District candidate Alice Candidate",
    }
    result = handlers["add_candidate"](
        {"name": "Alice Candidate", "party": "Democratic", "roster_sources": [base_source, second_source]}
    )
    assert "Added" in result
    assert len(race_json["candidates"][0]["roster_sources"]) == 2


def test_roster_sources_and_race_identity_handlers():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "ga-governor-2026", "candidates": [{"name": "Alice", "party": "Democratic"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    identity_result = handlers["set_race_identity"](
        {
            "office": "Governor",
            "state": "Georgia",
            "contest_stage": "post_primary_general",
            "election_date": "2026-11-03",
            "primary_status": "Major-party nominees certified.",
            "official_roster_source_url": "https://example.gov/candidates",
        }
    )
    source_result = handlers["set_candidate_roster_sources"](
        {
            "candidate_name": "Alice",
            "sources": [
                {
                    "url": "https://example.gov/candidates",
                    "type": "official",
                    "title": "Certified candidate list",
                    "evidence": "Alice is listed as a gubernatorial nominee.",
                    "published_at": "2026-06-10",
                    "race_id": "ga-governor-2026",
                    "evidence_tier": 1,
                    "retrieval_status": "content",
                }
            ],
        }
    )

    assert identity_result == "Recorded race identity brief."
    assert race_json["contest_stage"] == "post_primary_general"
    assert race_json["pipeline_state"]["race_identity"]["office"] == "Governor"
    assert "Set 1 roster source" in source_result
    assert race_json["candidates"][0]["roster_sources"][0]["type"] == "official"
    assert race_json["candidates"][0]["roster_sources"][0]["last_accessed"]


def test_federal_house_roster_rejects_same_number_state_house_evidence():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "al-house-02-2026", "state": "Alabama", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    source = {
        "url": "https://example.gov/alabama-house-2",
        "type": "official",
        "title": "Alabama House of Representatives District 2",
        "evidence": "Rick Pressnell is a candidate for Alabama House of Representatives District 2.",
        "published_at": "2026-01-15",
        "race_id": "al-house-02-2026",
        "evidence_tier": 1,
        "retrieval_status": "content",
    }

    result = handlers["add_candidate"]({"name": "Rick Pressnell", "party": "Democratic", "roster_sources": [source]})

    assert "Blocked adding" in result
    assert race_json["candidates"] == []


def test_federal_house_roster_accepts_official_search_result_shape_for_zero_padded_district():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "al-house-02-2026", "state": "Alabama", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    source = {
        "url": "https://aldemocrats.org/2026-qualified-candidates",
        "title": "2026 Primary Election - Qualified Candidates",
        "text": "US Representative, 2nd District - Shomari C. Figures",
        "retrieved": "2026-08-01",
    }

    result = handlers["add_candidate"]({"name": "Shomari Figures", "party": "Democratic", "roster_sources": [source]})

    assert "Added" in result
    saved = race_json["candidates"][0]["roster_sources"][0]
    assert saved["evidence"] == source["text"]
    assert saved["race_id"] == "al-house-02-2026"
    assert saved["type"] == "official"
    assert saved["evidence_tier"] == 3
    assert saved["retrieval_status"] == "snippet"


def test_wrong_contest_removal_requires_proof_and_physically_removes_contamination():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "id": "al-house-02-2026",
        "state": "Alabama",
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic"},
            {"name": "Rick Pressnell", "party": "Democratic"},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    source = {
        "url": "https://aldemocrats.org/2026-qualified-candidates",
        "type": "official",
        "title": "2026 qualified candidates",
        "evidence": "State Representative, District 2 - Rick Pressnell",
        "published_at": "2026-01-15",
        "evidence_tier": 1,
        "retrieval_status": "content",
    }

    result = handlers["remove_candidate"](
        {
            "name": "Rick Pressnell",
            "reason": "Official list places him in Alabama State House District 2, not U.S. House District 2.",
            "wrong_contest": True,
            "sources": [source],
        }
    )

    assert "wrong-contest" in result
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Shomari Figures"]


def test_wrong_contest_removal_accepts_native_official_search_evidence():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "id": "al-house-02-2026",
        "state": "Alabama",
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic"},
            {"name": "Ben Harrison", "party": "Republican"},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    source = {
        "url": "https://algop.org/qualified-2026-republican-candidates/",
        "title": "Qualified 2026 Republican Candidates",
        "text": "Alabama House of Representatives, District 2 — Ben Harrison",
        "retrieved": "2026-08-01",
    }

    result = handlers["remove_candidate"](
        {
            "name": "Ben Harrison",
            "reason": "The official party list places him in Alabama House District 2, not U.S. House District 2.",
            "wrong_contest": True,
            "sources": [source],
        }
    )

    assert "wrong-contest" in result
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Shomari Figures"]


def test_wrong_contest_removal_understands_negated_target_office():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "id": "al-house-02-2026",
        "candidates": [{"name": "Rick Pressnell"}, {"name": "Ben Harrison"}],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["remove_candidate"](
        {
            "name": "Rick Pressnell",
            "wrong_contest": True,
            "reason": "Official list places him in the state House contest.",
            "sources": [
                {
                    "url": "https://aldemocrats.org/2026-primary-election-qualified-candidates",
                    "title": "2026 Primary Election - Qualified Candidates",
                    "type": "official",
                    "evidence": (
                        "Lists State Representative, District 2 - Rick Pressnell under state legislative "
                        "candidates, confirming this is Alabama State House District 2, not U.S. House District 2"
                    ),
                    "retrieved": "2026-08-01",
                }
            ],
        }
    )

    assert result == "Removed wrong-contest candidate 'Rick Pressnell' from the active roster."
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Ben Harrison"]


def test_add_candidate_accepts_context_and_date_search_aliases():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "al-house-02-2026", "state": "Alabama", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    result = handlers["add_candidate"](
        {
            "name": "Shomari Figures",
            "party": "Democratic",
            "roster_sources": [
                {
                    "url": "https://aldemocrats.org/2026-primary-election-qualified-candidates",
                    "title": "2026 Primary Election - Qualified Candidates",
                    "context": "U.S. Representative, 2nd District - Shomari Figures",
                    "retrieved": "2026-08-01",
                    "date": "2026-02-01",
                }
            ],
        }
    )

    assert result == "Added candidate 'Shomari Figures'."
    source = race_json["candidates"][0]["roster_sources"][0]
    assert source["evidence"] == "U.S. Representative, 2nd District - Shomari Figures"
    assert source["published_at"] == "2026-02-01"


def test_add_candidate_accepts_native_search_snippet_alias():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "al-house-02-2026", "state": "Alabama", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    result = handlers["add_candidate"](
        {
            "name": "Shomari Figures",
            "party": "Democratic",
            "roster_sources": [
                {
                    "url": "https://aldemocrats.org/2026-qualified-candidates",
                    "title": "2026 Qualified Candidates",
                    "snippet": "US Representative, 2nd District - Shomari Figures",
                    "retrieved": "2026-08-01",
                }
            ],
        }
    )

    assert result == "Added candidate 'Shomari Figures'."
    assert race_json["candidates"][0]["roster_sources"][0]["evidence"].startswith("US Representative")


def test_add_candidate_accepts_evidence_text_but_requires_observed_url_in_agent_loop():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "al-house-02-2026", "state": "Alabama", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    source = {
        "url": "https://algop.org/special-congressional-election-qualified-candidates/",
        "title": "Special Congressional Election Qualified Candidates",
        "evidence_text": "2026 U.S. Congress Congressional District 2 qualified candidate Rhett Marques",
        "retrieved": "2026-08-01",
    }

    blocked = handlers["add_candidate"](
        {
            "name": "Rhett Marques",
            "party": "Republican",
            "roster_sources": [source],
            "_research_trace": {"researched_urls": [], "fetched_urls": []},
        }
    )
    assert "actual search/fetch trace" in blocked

    added = handlers["add_candidate"](
        {
            "name": "Rhett Marques",
            "party": "Republican",
            "roster_sources": [source],
            "_research_trace": {
                "researched_urls": [source["url"].rstrip("/")],
                "fetched_urls": [],
            },
        }
    )
    assert added == "Added candidate 'Rhett Marques'."
    saved = race_json["candidates"][0]["roster_sources"][0]
    assert saved["evidence"] == source["evidence_text"]
    assert saved["retrieval_status"] == "snippet"
    assert saved["evidence_tier"] == 3


def test_finalize_roster_requires_evidence_for_every_active_candidate():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {"race_identity": {"office": "U.S. House", "contest_stage": "pre_primary"}},
        "candidates": [
            {
                "name": "Shomari Figures",
                "party": "Democratic",
                "roster_sources": [
                    {
                        "url": "https://aldemocrats.org/2026-qualified-candidates",
                        "type": "official",
                        "title": "2026 Qualified Candidates",
                        "evidence": "US Representative, 2nd District - Shomari Figures",
                        "race_id": "al-house-02-2026",
                        "published_at": "2026-02-01",
                        "evidence_tier": 1,
                        "retrieval_status": "content",
                    }
                ],
            },
            {"name": "Unverified Candidate", "party": "Republican", "roster_sources": []},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    completeness_source = {
        "url": "https://aldemocrats.org/2026-qualified-candidates",
        "type": "official",
        "title": "2026 Qualified Candidates",
        "evidence": "Qualified candidates for U.S. Representative, 2nd Congressional District: Shomari Figures",
        "race_id": "al-house-02-2026",
        "published_at": "2026-02-01",
        "evidence_tier": 1,
        "retrieval_status": "content",
    }

    blocked = handlers["finalize_roster"]({"summary": "Official party lists", "completeness_sources": [completeness_source]})
    assert "Unverified Candidate" in blocked
    race_json["candidates"].pop()
    finalized = handlers["finalize_roster"]({"summary": "Official party list", "completeness_sources": [completeness_source]})
    assert finalized == "Roster finalized with 1 evidence-backed active candidate(s)."
    assert race_json["pipeline_state"]["roster_research"]["active_candidate_count"] == 1


def test_finalize_roster_requires_exact_special_election_completeness_source():
    from pipeline_client.agent.agent import _make_editing_handlers

    candidate_source = {
        "url": "https://algop.org/qualified-2026-republican-candidates/",
        "type": "official",
        "title": "Qualified 2026 Republican Candidates",
        "evidence": "U.S. Congress Congressional District 2 Hampton Harris",
        "race_id": "al-house-02-2026",
        "published_at": "2026-02-01",
        "evidence_tier": 1,
        "retrieval_status": "content",
    }
    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {
            "race_identity": {
                "office": "U.S. House",
                "contest_stage": "pre_primary",
                "primary_status": "Special Primary Election on August 11, 2026",
                "election_date": "2026-08-11",
            }
        },
        "candidates": [{"name": "Hampton Harris", "party": "Republican", "roster_sources": [candidate_source]}],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    ordinary = handlers["finalize_roster"]({"summary": "Regular primary list", "completeness_sources": [candidate_source]})
    assert "special election" in ordinary

    special_source = dict(candidate_source)
    special_source.update(
        {
            "url": "https://algop.org/special-congressional-election-qualified-candidates/",
            "title": "Special Congressional Election Qualified Candidates",
            "evidence": (
                "Qualified candidates for the August 11, 2026 Special Primary Election, U.S. Congress "
                "Congressional District 2: Hampton Harris"
            ),
            "published_at": "2026-05-22",
        }
    )
    searched_only = handlers["finalize_roster"](
        {
            "summary": "August special primary list",
            "completeness_sources": [special_source],
            "_research_trace": {"researched_urls": [special_source["url"]], "fetched_urls": []},
        }
    )
    assert "no sources were supplied" in searched_only
    finalized = handlers["finalize_roster"](
        {
            "summary": "August special primary list",
            "completeness_sources": [special_source],
            "_research_trace": {
                "researched_urls": [special_source["url"]],
                "fetched_urls": [special_source["url"]],
            },
        }
    )
    assert finalized == "Roster finalized with 1 evidence-backed active candidate(s)."


def test_finalize_roster_atomically_applies_complete_proposed_roster():
    from pipeline_client.agent.agent import _make_editing_handlers

    source_url = "https://elections.example.gov/2026-special-primary-certified-candidates"
    completeness_source = {
        "url": source_url,
        "type": "official",
        "title": "Certified Candidate List - Special Primary Election",
        "evidence": (
            "Certified candidates for the August 11, 2026 Special Primary Election for U.S. House "
            "Congressional District 2: Shomari Figures and Hampton Harris"
        ),
        "published_at": "2026-06-04",
    }
    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {
            "race_identity": {
                "office": "U.S. House",
                "contest_stage": "pre_primary",
                "primary_status": "Special Primary Election on August 11, 2026",
                "election_date": "2026-08-11",
            }
        },
        "candidates": [
            {"name": "Rick Pressnell", "party": "Democratic", "summary": "Wrong contest"},
            {"name": "Shomari Figures", "party": "Democratic", "summary": "Preserve this profile"},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["finalize_roster"](
        {
            "summary": "Official complete special-primary list",
            "candidates": [
                {"name": "Shomari Figures", "party": "Democratic", "incumbent": True},
                {"name": "Hampton Harris", "party": "Republican", "incumbent": False},
            ],
            "source_candidate_names": ["Shomari Figures", "Hampton Harris"],
            "completeness_sources": [completeness_source],
            "_research_trace": {"researched_urls": [source_url], "fetched_urls": [source_url]},
        }
    )

    assert result == "Roster finalized with 2 evidence-backed active candidate(s)."
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Shomari Figures", "Hampton Harris"]
    assert race_json["candidates"][0]["summary"] == "Preserve this profile"
    assert all(candidate["roster_sources"][0]["retrieval_status"] == "content" for candidate in race_json["candidates"])


def test_finalize_roster_infers_news_for_fetched_unlabeled_completeness_source():
    """Regression for the live AL-02 final synthesis payload."""
    from pipeline_client.agent.agent import _make_editing_handlers

    source_url = (
        "https://alabamareflector.com/2026/05/22/"
        "as-litigation-continues-21-candidates-qualify-for-august-alabama-congressional-primaries/"
    )
    source = {
        "url": source_url,
        "title": "Candidates qualify for August Alabama congressional primaries",
        "evidence": (
            "For the August 11, 2026 special primary in Alabama's 2nd Congressional District, "
            "Shomari Figures qualified with Republican candidates Rhett Marques, Hampton Harris, "
            "Christian Horn, David Matthews, Joshua McKee, and James Richardson."
        ),
        "published_at": "2026-05-22",
    }
    names = [
        "Shomari Figures",
        "Rhett Marques",
        "Hampton Harris",
        "Christian Horn",
        "David Matthews",
        "Joshua McKee",
        "James Richardson",
    ]
    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {
            "race_identity": {
                "office": "U.S. House",
                "contest_stage": "pre_primary",
                "primary_status": "Special Primary Election on August 11, 2026",
                "election_date": "2026-08-11",
            }
        },
        "candidates": [],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["finalize_roster"](
        {
            "summary": "Complete special-primary field reported by Alabama Reflector.",
            "candidates": [
                {"name": name, "party": "Democratic" if name == "Shomari Figures" else "Republican"} for name in names
            ],
            "source_candidate_names": names,
            "completeness_sources": [source],
            "_research_trace": {"researched_urls": [source_url], "fetched_urls": [source_url]},
        }
    )

    assert result == "Roster finalized with 7 evidence-backed active candidate(s)."
    audit_source = race_json["pipeline_state"]["roster_research"]["completeness_sources"][0]
    assert audit_source["type"] == "news"
    assert audit_source["retrieval_status"] == "content"
    assert audit_source["evidence_tier"] == 2


def test_fetched_unlabeled_candidate_source_does_not_gain_news_classification():
    from pipeline_client.agent.handlers import _normalize_observed_roster_sources

    source_url = "https://example.com/candidate-claim"
    sources = _normalize_observed_roster_sources(
        [{"url": source_url, "title": "Candidate claim", "evidence": "Alice Example is running in 2026."}],
        race_id="example-race-2026",
        research_trace={"researched_urls": [source_url], "fetched_urls": [source_url]},
    )

    assert sources[0]["type"] == "other"
    assert sources[0]["retrieval_status"] == "content"


def test_exact_contest_accepts_statewide_certification_table_row_wording():
    from pipeline_client.agent.handlers import _source_supports_exact_contest

    source = {
        "title": "State Certification of Republican Candidates Congressional Districts",
        "evidence": (
            "Certification for the Special Primary Election for U.S. Congressional Districts lists the following "
            "qualified candidates for District 2: Rhett Marques and Hampton Harris."
        ),
        "url": "https://www.sos.alabama.gov/certification.pdf",
    }

    assert _source_supports_exact_contest(source, race_id="al-house-02-2026") is True


def test_finalize_roster_atomic_submission_requires_extracted_name_match():
    from pipeline_client.agent.agent import _make_editing_handlers

    source_url = "https://elections.example.gov/certified-candidates"
    source = {
        "url": source_url,
        "type": "official",
        "title": "Certified Candidate List",
        "evidence": "2026 certified candidates for U.S. House Congressional District 2: Alice Example, Bob Example",
        "published_at": "2026-06-04",
    }
    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {"race_identity": {"office": "U.S. House", "contest_stage": "pre_primary"}},
        "candidates": [{"name": "Old Entry", "party": "Unknown"}],
    }
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["finalize_roster"](
        {
            "summary": "Incomplete extraction",
            "candidates": [{"name": "Alice Example", "party": "Democratic"}],
            "source_candidate_names": ["Alice Example", "Bob Example"],
            "completeness_sources": [source],
            "_research_trace": {"researched_urls": [source_url], "fetched_urls": [source_url]},
        }
    )

    assert "source_candidate_names must match" in result
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Old Entry"]


def test_finalize_roster_allows_middle_initial_in_extracted_source_name():
    from pipeline_client.agent.agent import _make_editing_handlers

    source_url = "https://aldemocrats.org/2026-primary-election-qualified-candidates"
    source = {
        "url": source_url,
        "title": "2026 Primary Election - Qualified Candidates",
        "evidence": (
            "Qualified candidate for the August 11, 2026 special primary for "
            "U.S. House Congressional District 2: Shomari C. Figures"
        ),
    }
    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {
            "race_identity": {
                "office": "U.S. House",
                "contest_stage": "pre_primary",
                "primary_status": "Special Primary Election on August 11, 2026",
                "election_date": "2026-08-11",
            }
        },
        "candidates": [],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["finalize_roster"](
        {
            "summary": "Official qualified candidate list.",
            "candidates": [{"name": "Shomari Figures", "party": "Democratic", "incumbent": True}],
            "source_candidate_names": ["Shomari C. Figures"],
            "completeness_sources": [source],
            "_research_trace": {"researched_urls": [source_url], "fetched_urls": [source_url]},
        }
    )

    assert result == "Roster finalized with 1 evidence-backed active candidate(s)."


def test_finalize_roster_reuses_persisted_content_evidence_by_url():
    from pipeline_client.agent.agent import _make_editing_handlers

    source_url = "https://www.sos.alabama.gov/2026/district-2-certified.pdf"
    trusted_source = {
        "url": source_url,
        "type": "official",
        "title": "State Certification of Candidates",
        "evidence": (
            "Certified and complete qualified candidate list for the August 11, 2026 Special Primary Election "
            "for U.S. House Congressional District 2: Shomari Figures and Hampton Harris"
        ),
        "race_id": "al-house-02-2026",
        "published_at": "2026-05-22",
        "evidence_tier": 1,
        "retrieval_status": "content",
    }
    race_json = {
        "id": "al-house-02-2026",
        "pipeline_state": {
            "race_identity": {
                "office": "U.S. House",
                "contest_stage": "pre_primary",
                "primary_status": "Special Primary Election on August 11, 2026",
                "election_date": "2026-08-11",
            }
        },
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic", "roster_sources": [trusted_source]},
            {"name": "Hampton Harris", "party": "Republican", "roster_sources": [trusted_source]},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["finalize_roster"](
        {
            "summary": "Reused official certification from the prior verified run.",
            "candidates": [
                {"name": "Shomari Figures", "party": "Democratic"},
                {"name": "Hampton Harris", "party": "Republican"},
            ],
            "source_candidate_names": ["Shomari Figures", "Hampton Harris"],
            "completeness_sources": [{"url": source_url, "title": "State Certification", "evidence": "model-provided claim"}],
            "_research_trace": {"researched_urls": [], "fetched_urls": []},
        }
    )

    assert result == "Roster finalized with 2 evidence-backed active candidate(s)."
    stored = race_json["pipeline_state"]["roster_research"]["completeness_sources"][0]
    assert stored["evidence"] == trusted_source["evidence"]


def test_add_candidate_blocks_primary_loser_after_nominee_is_known():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [
            {
                "name": "Fred Love",
                "party": "Democratic",
                "summary": "Fred Love is the Democratic nominee for Arkansas governor in 2026.",
            }
        ]
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["add_candidate"]({"name": "Supha Xayprasith-Mays", "party": "Democratic"})

    assert "Blocked adding" in result
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Fred Love"]


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


def test_remove_candidate_blocks_not_listed_without_exit_signal():
    """remove_candidate requires an explicit exit signal, not just absence from a source."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "D"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"](
        {
            "name": "Alice",
            "reason": "Ballotpedia and other sources do not list Alice as a candidate for this race.",
        }
    )

    assert "blocked" in result.lower()
    assert race_json["candidates"] == [{"name": "Alice", "party": "D"}]


def test_remove_candidate_allows_former_officeholder_not_running():
    """A retired former officeholder who is not a candidate this cycle can be removed.

    Regression: nc-house-01 kept G.K. Butterfield (U.S. Rep who left office in 2023)
    because the guard only accepted withdrawal/primary-loss reasons.
    """
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Don Davis", "party": "D"}, {"name": "G.K. Butterfield", "party": "D"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"](
        {
            "name": "G.K. Butterfield",
            "reason": "Former U.S. Representative who retired in 2022 and is not a candidate in the 2026 election.",
        }
    )

    assert "blocked" not in result.lower()
    butterfield = next(c for c in race_json["candidates"] if c["name"] == "G.K. Butterfield")
    assert butterfield.get("withdrawn") is True


def test_remove_candidate_blocks_generic_primary_loss_without_official_result():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "D"}, {"name": "Bob", "party": "R"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"]({"name": "Alice", "reason": "Lost primary election"})

    assert "blocked" in result.lower()
    assert race_json["candidates"][0].get("withdrawn") is not True


def test_remove_candidate_accepts_dated_primary_loss_without_official_keyword():
    """A specific dated primary-loss reason is sufficient corroboration on its own —
    requiring the literal word 'official' in addition to a real date blocked
    reasonable model output like 'Lost the Democratic primary on June 30, 2026.'
    in a post_primary_general race, leaving primary losers stuck on the roster."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Chris Baum", "party": "Unknown"}, {"name": "Manny Rutinel", "party": "D"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"]({"name": "Chris Baum", "reason": "Lost the Democratic primary on June 30, 2026."})

    assert "blocked" not in result.lower()
    assert race_json["candidates"][0]["withdrawn"] is True


def test_remove_candidate_blocks_when_it_would_empty_roster():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "party": "D"}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"]({"name": "Alice", "reason": "officially withdrew from the race"})

    assert "blocked" in result.lower()
    assert race_json["candidates"][0].get("withdrawn") is not True


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


def test_set_issue_stance_rejects_placeholder_variants():
    """A placeholder stance like 'To be determined after review' must be rejected
    outright — not just the bare exact marker 'to be determined'. This is the
    literal defect that let a placeholder ship in a published race."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "issues": {}}]}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    for placeholder in ["To be determined after review", "TBD", "Pending further research", "  "]:
        result = handlers["set_issue_stance"](
            {
                "candidate_name": "Alice",
                "issue": "Healthcare",
                "stance": placeholder,
                "confidence": "low",
            }
        )
        assert "ERROR" in result, f"expected rejection for {placeholder!r}, got: {result}"
        assert "Healthcare" not in race_json["candidates"][0]["issues"]

    # The sanctioned no-position fallback must still be accepted.
    ok = handlers["set_issue_stance"](
        {
            "candidate_name": "Alice",
            "issue": "Healthcare",
            "stance": "No public position found after repeated research attempts.",
            "confidence": "low",
        }
    )
    assert "ERROR" not in ok
    assert race_json["candidates"][0]["issues"]["Healthcare"]["stance"] == (
        "No public position found after repeated research attempts."
    )


def test_is_missing_stance_text_catches_placeholder_variants_not_just_exact_markers():
    """Exact-match-only detection missed variants like 'To be determined after
    review' — this covers the broadened prefix+length-bounded check."""
    from pipeline_client.agent.agent import _is_missing_stance_text

    assert _is_missing_stance_text("")
    assert _is_missing_stance_text("   ")
    assert _is_missing_stance_text("to be determined")
    assert _is_missing_stance_text("To be determined after review")
    assert _is_missing_stance_text("TBD")
    assert _is_missing_stance_text("Pending further research")
    assert _is_missing_stance_text("No public position found after repeated research attempts.")

    # Real stances must not be caught, including ones that start with a marker word
    # as part of a genuine, longer sentence.
    assert not _is_missing_stance_text("Supports universal healthcare coverage for all residents.")
    assert not _is_missing_stance_text(
        "Missing and murdered Indigenous women (MMIW) has been a signature policy "
        "priority throughout the campaign, with several proposed task forces."
    )


def test_restrict_to_candidate_blocks_edits_to_other_candidates():
    """restrict_to_candidate must reject candidate-targeting tool calls naming a
    different candidate — this is the guard against the review-iteration pass
    silently corrupting one candidate's data while processing another's turn."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [
            {"name": "Alice", "issues": {}},
            {"name": "Bob", "issues": {}},
        ]
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None, restrict_to_candidate="Alice")

    blocked = handlers["set_issue_stance"](
        {
            "candidate_name": "Bob",
            "issue": "Healthcare",
            "stance": "Should not be applied.",
            "confidence": "high",
        }
    )
    assert "ERROR" in blocked
    assert race_json["candidates"][1]["issues"] == {}, "Bob's data must be untouched"

    allowed = handlers["set_issue_stance"](
        {
            "candidate_name": "Alice",
            "issue": "Healthcare",
            "stance": "Supports universal coverage.",
            "confidence": "high",
            "sources": [{"url": "https://example.com/alice-healthcare"}],
        }
    )
    assert "ERROR" not in allowed
    assert race_json["candidates"][0]["issues"]["Healthcare"]["stance"] == "Supports universal coverage."


def test_restrict_to_candidate_does_not_affect_unscoped_handlers():
    """Tools with no candidate_name (or that are read-only / race-wide) are unaffected."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Alice", "issues": {}}], "polling": []}
    handlers = _make_editing_handlers(race_json, lambda l, m: None, restrict_to_candidate="Alice")

    result = handlers["update_race_field"]({"field": "office", "value": "Governor"})
    assert "ERROR" not in result


def test_remove_candidate_source_url_removes_all_candidate_occurrences():
    """remove_candidate_source_url removes a URL from every candidate source slot."""
    from pipeline_client.agent.agent import _make_editing_handlers

    bad_url = "https://example.com/dead"
    race_json = {
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [{"url": bad_url}, {"url": "https://example.com/good-summary"}],
                "donor_source_url": bad_url,
                "donor_sources": [{"url": bad_url}],
                "voting_source_url": bad_url,
                "voting_sources": [{"url": bad_url}, {"url": "https://example.com/good-votes"}],
                "links": [{"url": bad_url, "title": "Dead", "type": "news"}],
                "issues": {
                    "Healthcare": {
                        "stance": "Supports coverage.",
                        "confidence": "high",
                        "sources": [{"url": bad_url}, {"url": "https://example.com/good-health"}],
                    }
                },
            }
        ]
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate_source_url"]({"candidate_name": "Alice", "url": bad_url})

    candidate = race_json["candidates"][0]
    serialized = json.dumps(candidate)
    assert "Removed 7 occurrence" in result
    assert bad_url not in serialized
    assert "https://example.com/good-summary" in serialized
    assert "https://example.com/good-votes" in serialized
    assert "https://example.com/good-health" in serialized
    assert candidate["donor_source_url"] is None
    assert candidate["voting_source_url"] is None


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

    candidate = handlers["read_profile"]({"section": "candidate", "candidate_name": "Alice"})
    assert json.loads(candidate)["name"] == "Alice"

    full = handlers["read_profile"]({"section": "full"})
    assert "\n" not in full


def test_update_race_field_rejects_title_like_description():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "title": "2026 United States Senate election in Arkansas",
        "description": (
            "Arkansas voters will elect a U.S. senator on November 3, 2026. Republican incumbent Tom Cotton faces "
            "Democrat Hallie Shoffner and Libertarian Jeff Wadlin. The contest will determine who represents the "
            "state and will contribute to the Senate's partisan balance."
        ),
        "candidates": [],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["update_race_field"]({"field": "description", "value": "2026 United States Senate election in Arkansas"})

    assert result.startswith("ERROR:")
    assert race_json["description"].startswith("Arkansas voters")


def test_update_race_field_accepts_substantive_description():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"title": "2026 United States Senate election in Arkansas", "description": "", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda *_: None)
    description = (
        "Arkansas voters will elect a U.S. senator on November 3, 2026. Republican incumbent Tom Cotton faces "
        "Democrat Hallie Shoffner and Libertarian Jeff Wadlin. Arkansas has favored Republicans in recent statewide "
        "federal elections. The candidates offer different approaches to economic policy, immigration, agriculture, "
        "and the role of the federal government."
    )

    result = handlers["update_race_field"]({"field": "description", "value": description})

    assert result == "Updated race.description."
    assert race_json["description"] == description


def test_update_race_field_normalizes_house_ballotpedia_to_district_page():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"id": "ar-house-03-2026", "candidates": []}
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["update_race_field"](
        {
            "field": "ballotpedia_url",
            "value": "https://ballotpedia.org/Arkansas%27_3rd_Congressional_District_election,_2026",
        }
    )

    assert result == "Updated race.ballotpedia_url."
    assert race_json["ballotpedia_url"] == "https://ballotpedia.org/Arkansas'_3rd_Congressional_District"


def test_remove_poll_handler():
    """remove_poll handler deletes polls by pollster+date or pollster alone."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [],
        "polling": [
            {"pollster": "SurveyUSA", "date": "2026-03-01", "matchups": [], "source_url": "https://a.com"},
            {"pollster": "SurveyUSA", "date": "2026-03-01", "matchups": [], "source_url": "https://b.com"},
            {"pollster": "Emerson", "date": "2026-02-01", "matchups": [], "source_url": "https://c.com"},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    # Remove by pollster+date removes both duplicates
    result = handlers["remove_poll"]({"pollster": "SurveyUSA", "date": "2026-03-01", "reason": "duplicate"})
    assert "2" in result or "Removed" in result
    assert all(p["pollster"] != "SurveyUSA" for p in race_json["polling"])
    assert len(race_json["polling"]) == 1

    # Remove by pollster only
    handlers["remove_poll"]({"pollster": "Emerson", "reason": "null data"})
    assert race_json["polling"] == []


def test_finalize_metadata_atomically_requires_complete_sourced_roster():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "id": "al-house-02-2026",
        "description": "Old description",
        "candidates": [
            {"name": "Alice Example", "summary": "", "summary_sources": []},
            {"name": "Bob Example", "summary": "", "summary_sources": []},
        ],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)
    source = {"url": "https://example.com/race", "type": "news", "title": "Race guide"}
    trace = {"researched_urls": [source["url"]], "fetched_urls": []}

    incomplete = handlers["finalize_metadata"](
        {
            "description": "This is a substantive description of the exact election and its broader context. "
            "It explains the office, timing, field, and major contrasts without advocating for a candidate.",
            "description_sources": [source],
            "candidates": [
                {
                    "name": "Alice Example",
                    "summary": "Alice Example is a candidate with relevant public service and professional experience. "
                    "Her biography describes that background in neutral language for voters.",
                    "sources": [source],
                }
            ],
            "_research_trace": trace,
        }
    )
    assert incomplete.startswith("ERROR:")
    assert race_json["description"] == "Old description"

    complete = handlers["finalize_metadata"](
        {
            "description": "This is a substantive description of the exact election and its broader context. "
            "It explains the office, timing, field, and major contrasts without advocating for a candidate.",
            "description_sources": [source],
            "candidates": [
                {
                    "name": "Alice Example",
                    "summary": "Alice Example is a candidate with relevant public service and professional experience. "
                    "Her biography describes that background in neutral language for voters.",
                    "sources": [source],
                },
                {
                    "name": "Bob Example",
                    "summary": "Bob Example is a candidate with relevant community leadership and professional experience. "
                    "His biography describes that background in neutral language for voters.",
                    "sources": [source],
                },
            ],
            "_research_trace": trace,
        }
    )
    assert complete.startswith("Metadata finalized")
    assert all(candidate["summary"] for candidate in race_json["candidates"])
    assert race_json["pipeline_state"]["metadata_research"]["active_candidate_count"] == 2


def test_remove_poll_blocks_full_roster_alignment_for_primary_matchup():
    from pipeline_client.agent.agent import _make_editing_handlers

    poll = {
        "pollster": "Peak Insights",
        "date": "2026-06-09",
        "matchups": [{"candidates": ["Rhett Marques", "Hampton Harris"], "percentages": [30, 4]}],
        "source_url": "https://example.com/republican-primary-poll",
    }
    race_json = {
        "candidates": [
            {"name": "Shomari Figures", "party": "Democratic"},
            {"name": "Rhett Marques", "party": "Republican"},
            {"name": "Hampton Harris", "party": "Republican"},
        ],
        "polling": [poll],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["remove_poll"](
        {
            "pollster": "Peak Insights",
            "date": "2026-06-09",
            "reason": "Roster alignment: poll did not include Shomari Figures.",
        }
    )

    assert result.startswith("ERROR: Poll removal blocked")
    assert race_json["polling"] == [poll]


def test_add_poll_requires_exact_roster_names():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    rejected = handlers["add_poll"](
        {
            "pollster": "Reliable Research",
            "date": "2026-06-01",
            "matchups": [{"candidates": ["Alice", "Bob Jones"], "percentages": [48, 45]}],
            "source_url": "https://example.com/poll",
        }
    )
    accepted = handlers["add_poll"](
        {
            "pollster": "Reliable Research",
            "date": "2026-06-01",
            "matchups": [{"candidates": ["Alice Smith", "Bob Jones"], "percentages": [48, 45]}],
            "source_url": "https://example.com/poll",
        }
    )

    assert rejected.startswith("ERROR:")
    assert accepted.startswith("Added poll")
    assert len(race_json["polling"]) == 1


def test_add_poll_allows_source_only_poll_but_rejects_incomplete_matchups():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [{"name": "Alice Smith"}, {"name": "Bob Jones"}],
        "polling": [],
    }
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    source_only = handlers["add_poll"](
        {
            "pollster": "Example Source Only Poll",
            "date": "2026-06-01",
            "matchups": [],
            "source_url": "https://example.com/source-only-poll",
        }
    )
    missing = handlers["add_poll"](
        {
            "pollster": "Reliable Research",
            "date": "2026-06-01",
            "matchups": [{"candidates": ["Alice Smith", "Bob Jones"]}],
            "source_url": "https://example.com/poll",
        }
    )
    mismatched = handlers["add_poll"](
        {
            "pollster": "Reliable Research",
            "date": "2026-06-01",
            "matchups": [{"candidates": ["Alice Smith", "Bob Jones"], "percentages": [48]}],
            "source_url": "https://example.com/poll",
        }
    )

    assert source_only.startswith("Added poll")
    assert missing.startswith("ERROR:")
    assert mismatched.startswith("ERROR:")
    assert [poll["pollster"] for poll in race_json["polling"]] == ["Example Source Only Poll"]


def test_remove_candidate_deletes_malformed_entries():
    """remove_candidate physically deletes entries whose name looks like a metadata key."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [
            {"name": "Alice Smith", "issues": {}},
            {"name": "updated_utc", "issues": {}},
        ],
        "polling": [],
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["remove_candidate"]({"name": "updated_utc", "reason": "metadata key, not a real candidate"})
    assert "Deleted" in result or "deleted" in result.lower()
    names = [c["name"] for c in race_json["candidates"]]
    assert "updated_utc" not in names
    assert "Alice Smith" in names


def test_remove_candidate_does_not_delete_real_names():
    """remove_candidate marks real candidate names as withdrawn, not deleted."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {
        "candidates": [{"name": "Bob Jones", "issues": {}}, {"name": "Alice Smith", "issues": {}}],
        "polling": [],
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    handlers["remove_candidate"]({"name": "Bob Jones", "reason": "withdrew from race"})
    assert len(race_json["candidates"]) == 2
    assert race_json["candidates"][0].get("withdrawn") is True


def test_remove_candidate_accepts_completed_primary_loss_with_last_updated_context():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Brad Raffensperger"}, {"name": "Burt Jones"}]}
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["remove_candidate"](
        {
            "name": "Brad Raffensperger",
            "reason": (
                "Official Georgia Secretary of State results show Brad Raffensperger "
                "lost the Republican primary on May 19, 2026, before the profile's "
                "last_updated date of June 13, 2026."
            ),
        }
    )

    assert "blocked" not in result.lower()
    assert race_json["candidates"][0]["withdrawn"] is True


# ---------------------------------------------------------------------------
# Search cache
# ---------------------------------------------------------------------------


def test_search_cache_list_cached_for_race():
    """SearchCache.list_cached_for_race returns cached queries."""
    from pipeline_client.agent.search_cache import SearchCache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = SearchCache(cache_dir=tmpdir, default_ttl_hours=168)
        cache.set("test query", [{"title": "R", "snippet": "...", "url": "https://r.com"}], race_id="test-race")

        result = cache.list_cached_for_race("test-race")
        assert len(result["searches"]) == 1
        assert result["searches"][0]["query"] == "test query"
        assert "https://r.com" in result["searches"][0]["urls"]


def _nj_race_json():
    return {
        "id": "nj-senate-2026",
        "state": "New Jersey",
        "candidates": [
            {"name": "Cory Booker", "party": "Democratic"},
            {"name": "Veronica Fernandez", "party": "Unknown"},
        ],
    }


def _nj_ballotpedia_source(source_type):
    """The exact source shape the roster agent emitted for nj-senate-2026."""
    source = {
        "url": "https://ballotpedia.org/United_States_Senate_election_in_New_Jersey,_2026",
        "title": "United States Senate election in New Jersey, 2026",
        "text": (
            "Incumbent Cory Booker, Justin Murphy, Veronica Fernandez, and Joanne Kuniansky are "
            "running in the general election for U.S. Senate New Jersey on November 3, 2026"
        ),
        "retrieved": "2026-08-01",
    }
    if source_type is not None:
        source["type"] = source_type
    return source


@pytest.mark.parametrize("source_type", ["web", "election_authority", "encyclopedia", None])
def test_roster_source_type_inferred_from_host_for_unrecognized_labels(source_type):
    """An unrecognized-but-plausible type label must not strand evidence in 'other'."""
    from pipeline_client.agent.handlers import _normalize_roster_source

    normalized = _normalize_roster_source(_nj_ballotpedia_source(source_type), race_id="nj-senate-2026")

    assert normalized["type"] == "ballotpedia"


def test_set_candidate_roster_sources_accepts_single_source_for_existing_candidate():
    """Attaching evidence to a candidate already on the roster needs no corroboration."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_race_json()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["set_candidate_roster_sources"](
        {"candidate_name": "Veronica Fernandez", "sources": [_nj_ballotpedia_source("web")]}
    )

    assert "Set 1 roster source(s)" in result
    assert race_json["candidates"][1]["roster_sources"][0]["type"] == "ballotpedia"


def test_add_candidate_still_requires_corroboration_for_tier3_snippets():
    """The anti-fabrication gate on *new* candidates is unchanged."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_race_json()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["add_candidate"](
        {
            "name": "Joanne Kuniansky",
            "party": "Socialist Workers Party",
            "roster_sources": [_nj_ballotpedia_source("web")],
        }
    )

    assert "Blocked adding" in result
    assert [candidate["name"] for candidate in race_json["candidates"]] == ["Cory Booker", "Veronica Fernandez"]


def test_self_declared_official_type_cannot_waive_corroboration():
    """A model must not grant itself official authority by relabelling an arbitrary host."""
    from pipeline_client.agent.handlers import _classify_roster_source_type, _qualifying_candidate_addition_sources

    assert _classify_roster_source_type("official", title="T", url="https://randomblog.com/p", host="randomblog.com") == "news"

    sources = [
        {
            "url": "https://randomblog.com/p",
            "type": "official",
            "title": "Veronica Fernandez 2026",
            "evidence": "Veronica Fernandez is running for U.S. Senate New Jersey in 2026",
        }
    ]
    assert _qualifying_candidate_addition_sources(sources, candidate_name="Veronica Fernandez", race_id="nj-senate-2026") == []


def test_blocked_roster_edit_names_the_failing_check():
    """A generic 'need better evidence' message sends the model hunting for the wrong thing."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_race_json()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    missing_evidence = handlers["set_candidate_roster_sources"](
        {
            "candidate_name": "Veronica Fernandez",
            "sources": [
                {
                    "url": "https://ballotpedia.org/x",
                    "type": "ballotpedia",
                    "title": "United States Senate election in New Jersey, 2026",
                }
            ],
        }
    )
    assert "evidence" in missing_evidence.lower()

    wrong_name = handlers["set_candidate_roster_sources"](
        {
            "candidate_name": "Veronica Fernandez",
            "sources": [_nj_ballotpedia_source("web") | {"text": "Cory Booker is running in 2026"}],
        }
    )
    assert "candidate name" in wrong_name.lower()


# ---------------------------------------------------------------------------
# Roster-absence removal ("never was a candidate here")
# ---------------------------------------------------------------------------


def _nj_roster_race():
    return {
        "id": "nj-senate-2026",
        "state": "New Jersey",
        "office": "U.S. Senate",
        "candidates": [
            {"name": "Cory Booker", "party": "Democratic", "incumbent": True},
            {"name": "Justin Murphy", "party": "Republican"},
            {"name": "Veronica Fernandez", "party": "Independent"},
            {"name": "Justin Maldonado", "party": "Unknown"},
        ],
    }


def _nj_roster_listing():
    """A real Ballotpedia race-page snippet that enumerates the field."""
    return {
        "url": "https://ballotpedia.org/United_States_Senate_election_in_New_Jersey,_2026",
        "type": "ballotpedia",
        "title": "United States Senate election in New Jersey, 2026",
        "text": (
            "Incumbent Cory Booker, Justin Murphy, Veronica Fernandez, and Joanne Kuniansky are "
            "running in the general election for U.S. Senate New Jersey on November 3, 2026"
        ),
        "retrieved": "2026-08-01",
    }


def test_not_on_roster_removes_phantom_candidate_with_roster_listing():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["remove_candidate"](
        {
            "name": "Justin Maldonado",
            "reason": "No evidence of candidacy; absent from the race roster listing.",
            "not_on_roster": True,
            "sources": [_nj_roster_listing()],
        }
    )

    assert "unlisted" in result
    assert "Justin Maldonado" not in [candidate["name"] for candidate in race_json["candidates"]]


def test_not_on_roster_rejects_a_listing_that_does_not_enumerate_the_field():
    """A blocked or truncated page must not read as proof of absence."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    empty_page = _nj_roster_listing() | {
        "text": "United States Senate election in New Jersey, 2026. Please enable JavaScript."
    }

    result = handlers["remove_candidate"](
        {"name": "Justin Maldonado", "reason": "Not found anywhere.", "not_on_roster": True, "sources": [empty_page]}
    )

    assert "blocked" in result.lower()
    assert "Justin Maldonado" in [candidate["name"] for candidate in race_json["candidates"]]


def test_not_on_roster_allows_evidence_that_narrates_the_omission():
    """The natural way to describe an omission names the omitted person.

    Regression guard: scanning the evidence prose for the candidate's name
    rejected every correctly-reasoned removal, because models write things like
    "enumerates the field without Justin Maldonado".
    """
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    listing = _nj_roster_listing()
    listing["text"] += (
        ". This enumerates the complete general election field without Justin Maldonado, "
        "who is listed under 'Withdrawn or disqualified candidates'."
    )

    result = handlers["remove_candidate"](
        {"name": "Justin Maldonado", "reason": "No evidence of candidacy.", "not_on_roster": True, "sources": [listing]}
    )

    assert "unlisted" in result
    assert "Justin Maldonado" not in [candidate["name"] for candidate in race_json["candidates"]]


def test_not_on_roster_rejects_listing_that_affirmatively_names_target():
    """A model's contradictory reason cannot turn roster proof into absence proof."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    listing = _nj_roster_listing()
    listing["text"] = (
        "Official candidate list for United States Senate New Jersey, 2026: Cory Booker, "
        "Justin Maldonado, Justin Murphy, and Veronica Fernandez."
    )

    result = handlers["remove_candidate"](
        {
            "name": "Justin Maldonado",
            "reason": "The official list does not include this candidate.",
            "not_on_roster": True,
            "sources": [listing],
        }
    )

    assert "blocked" in result.lower()
    assert "Justin Maldonado" in [candidate["name"] for candidate in race_json["candidates"]]


def test_not_on_roster_still_requires_two_corroborating_roster_names():
    """The structural guarantee: the listing must independently name current roster members."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    thin = _nj_roster_listing()
    thin["text"] = "Cory Booker is running in the general election for U.S. Senate New Jersey in 2026."

    result = handlers["remove_candidate"](
        {"name": "Justin Maldonado", "reason": "No evidence.", "not_on_roster": True, "sources": [thin]}
    )

    assert "blocked" in result.lower()
    assert "Justin Maldonado" in [candidate["name"] for candidate in race_json["candidates"]]


def test_not_on_roster_refuses_to_remove_the_incumbent():
    """An incumbent missing from one snippet is a bad snippet, not a phantom."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)
    listing = _nj_roster_listing()
    listing["text"] = "Justin Murphy, Veronica Fernandez, and Joanne Kuniansky are running in 2026"

    result = handlers["remove_candidate"](
        {"name": "Cory Booker", "reason": "Absent from listing.", "not_on_roster": True, "sources": [listing]}
    )

    assert "incumbent" in result.lower()
    assert "Cory Booker" in [candidate["name"] for candidate in race_json["candidates"]]


def test_wrong_contest_removal_works_for_non_house_races():
    """Wrong-contest proof was previously impossible for anything but a U.S. House race."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["remove_candidate"](
        {
            "name": "Justin Maldonado",
            "reason": "Official filing list places him in the New Jersey General Assembly race, not U.S. Senate.",
            "wrong_contest": True,
            "sources": [
                {
                    "url": "https://www.nj.gov/state/elections/2026-candidates.html",
                    "title": "2026 Certified Candidates",
                    "text": "General Assembly District 24 - Justin Maldonado",
                    "published_at": "2026-06-10",
                }
            ],
        }
    )

    assert "wrong-contest" in result
    assert "Justin Maldonado" not in [candidate["name"] for candidate in race_json["candidates"]]


def test_cited_evidence_waives_the_withdrawal_keyword_scan():
    """A real current-cycle source naming the candidate beats prose phrasing."""
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = _nj_roster_race()
    handlers = _make_editing_handlers(race_json, lambda _level, _message: None)

    result = handlers["remove_candidate"](
        {
            "name": "Justin Maldonado",
            # Deliberately avoids every _EXIT_KEYWORDS phrase.
            "reason": "His campaign ended before the filing deadline.",
            "sources": [
                {
                    "url": "https://newjerseyglobe.com/congress/maldonado-ends-bid/",
                    "type": "news",
                    "title": "Justin Maldonado ends U.S. Senate bid",
                    "text": "Justin Maldonado will not appear on the 2026 ballot.",
                    "published_at": "2026-06-10",
                }
            ],
        }
    )

    assert "withdrawn" in result.lower()


def test_completeness_gate_accepts_real_secretary_of_state_list_phrasing():
    """New Jersey publishes "Official List Candidates ..." — the certified field itself."""
    from pipeline_client.agent.handlers import _normalize_roster_source, _roster_completeness_source_rejection_reason

    source = _normalize_roster_source(
        {
            "url": "https://www.nj.gov/state/elections/assets/pdf/election-results/2026/2026-official-general-candidates-us-senate.pdf",
            "title": "Official List Candidates for US Senate For GENERAL ELECTION 11/03/2026",
            "evidence": (
                "07/27/2026 Official List Candidates for US Senate For GENERAL ELECTION 11/03/2026: "
                "CORY BOOKER (Democratic), JUSTIN MURPHY (Republican), VERONICA FERNANDEZ, JOANNE KUNIANSKY."
            ),
            "race_id": "nj-senate-2026",
            "published_at": "2026-07-27T00:00:00Z",
            "evidence_tier": 1,
            "retrieval_status": "content",
        },
        race_id="nj-senate-2026",
    )

    assert source["type"] == "official"
    assert (
        _roster_completeness_source_rejection_reason(
            source,
            race_id="nj-senate-2026",
            identity={"office": "U.S. Senate", "contest_stage": "post_primary_general"},
        )
        is None
    )


def test_completeness_gate_still_rejects_single_candidate_evidence():
    """A page about one candidate proves membership, never completeness."""
    from pipeline_client.agent.handlers import _normalize_roster_source, _roster_completeness_source_rejection_reason

    source = _normalize_roster_source(
        {
            "url": "https://www.nj.gov/state/elections/some-profile",
            "title": "Cory Booker profile",
            "evidence": "Cory Booker is the incumbent senator seeking re-election in 2026.",
            "race_id": "nj-senate-2026",
            "published_at": "2026-07-27T00:00:00Z",
            "evidence_tier": 1,
            "retrieval_status": "content",
        },
        race_id="nj-senate-2026",
    )

    assert _roster_completeness_source_rejection_reason(
        source, race_id="nj-senate-2026", identity={"office": "U.S. Senate", "contest_stage": "post_primary_general"}
    )
