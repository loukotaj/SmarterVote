"""Tests for editing tool handlers, roster sync, candidate targeting, and search cache."""

import json
import tempfile

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

    assert len(ROSTER_TOOLS) == 5
    assert len(CANDIDATE_TOOLS) == 2
    assert len(ISSUE_TOOLS) == 1
    assert len(RECORD_TOOLS) == 4  # donor_summary, voting_summary, add_link, remove_candidate_source_url
    assert len(RACE_TOOLS) == 3
    assert SET_FORECAST_TOOL["function"]["name"] == "set_forecast"
    assert SET_CANDIDATE_ROSTER_SOURCES_TOOL["function"]["name"] == "set_candidate_roster_sources"
    assert SET_RACE_IDENTITY_TOOL["function"]["name"] == "set_race_identity"
    assert READ_PROFILE_TOOL["function"]["name"] == "read_profile"


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
        "set_candidate_field",
        "set_candidate_summary",
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
