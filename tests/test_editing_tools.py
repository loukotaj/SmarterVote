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
        SET_CANDIDATE_SUMMARY_TOOL,
        SET_DONOR_SUMMARY_TOOL,
        SET_FORECAST_TOOL,
        SET_ISSUE_STANCE_TOOL,
        SET_VOTING_SUMMARY_TOOL,
        UPDATE_RACE_FIELD_TOOL,
    )

    assert len(ROSTER_TOOLS) == 3
    assert len(CANDIDATE_TOOLS) == 2
    assert len(ISSUE_TOOLS) == 1
    assert len(RECORD_TOOLS) == 3  # donor_summary, voting_summary, add_link
    assert len(RACE_TOOLS) == 3
    assert SET_FORECAST_TOOL["function"]["name"] == "set_forecast"
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
        "set_candidate_field",
        "set_candidate_summary",
        "set_issue_stance",
        "set_donor_summary",
        "set_voting_summary",
        "add_candidate_link",
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
            "based_on_poll_count": 1,
            "source_urls": ["https://example.com/poll"],
        }
    )

    assert result == "Updated race.forecast."
    assert race_json["forecast"]["rating"] == "lean_d"
    assert race_json["forecast"]["win_probability"] == 0.72
    assert race_json["forecast"]["generated_at"]


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

    race_json = {"candidates": []}
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    result = handlers["add_candidate"]({"name": "Alice", "party": "Democratic"})
    assert "Added" in result
    assert len(race_json["candidates"]) == 1
    assert race_json["candidates"][0]["name"] == "Alice"


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
            "pollster": "Example Poll",
            "date": "2026-06-01",
            "matchups": [{"candidates": ["Alice", "Bob Jones"], "percentages": [48, 45]}],
            "source_url": "https://example.com/poll",
        }
    )
    accepted = handlers["add_poll"](
        {
            "pollster": "Example Poll",
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
            "pollster": "Example Poll",
            "date": "2026-06-01",
            "matchups": [{"candidates": ["Alice Smith", "Bob Jones"]}],
            "source_url": "https://example.com/poll",
        }
    )
    mismatched = handlers["add_poll"](
        {
            "pollster": "Example Poll",
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
        "candidates": [{"name": "Bob Jones", "issues": {}}],
        "polling": [],
    }
    handlers = _make_editing_handlers(race_json, lambda l, m: None)

    handlers["remove_candidate"]({"name": "Bob Jones", "reason": "withdrew from race"})
    assert len(race_json["candidates"]) == 1
    assert race_json["candidates"][0].get("withdrawn") is True


def test_remove_candidate_accepts_completed_primary_loss_with_last_updated_context():
    from pipeline_client.agent.agent import _make_editing_handlers

    race_json = {"candidates": [{"name": "Brad Raffensperger"}]}
    handlers = _make_editing_handlers(race_json, lambda *_: None)

    result = handlers["remove_candidate"](
        {
            "name": "Brad Raffensperger",
            "reason": ("Lost Republican primary on May 19, 2026, before the profile's " "last_updated date of June 13, 2026."),
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
