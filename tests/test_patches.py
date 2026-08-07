"""Behavioral tests for pipeline_client.agent.patches merge/patch helpers.

These are pure dict-mutation functions with no external dependencies, and
previously had zero direct test coverage (8%).
"""

from unittest.mock import MagicMock

from pipeline_client.agent.patches import (
    _apply_candidate_patch,
    _apply_finance_patch,
    _apply_issue_patch,
    _apply_meta_patch,
    _apply_refine_patch,
    _summarize_existing_stances,
)


def _log():
    return MagicMock()


# ---------------------------------------------------------------------------
# _apply_meta_patch
# ---------------------------------------------------------------------------


def test_apply_meta_patch_updates_description():
    race_json = {"description": "old"}
    _apply_meta_patch(race_json, {"description": "new description"}, _log())
    assert race_json["description"] == "new description"


def test_apply_meta_patch_ignores_empty_description():
    race_json = {"description": "old"}
    _apply_meta_patch(race_json, {"description": ""}, _log())
    assert race_json["description"] == "old"


def test_apply_meta_patch_dedupes_and_prepends_new_polls():
    race_json = {"polling": [{"source": "Poll A", "date": "2026-01-01"}]}
    patch = {
        "polling": [
            {"source": "Poll A", "date": "2026-01-01"},  # duplicate, should be dropped
            {"source": "Poll B", "date": "2026-02-01"},
        ]
    }
    _apply_meta_patch(race_json, patch, _log())

    assert race_json["polling"] == [
        {"source": "Poll B", "date": "2026-02-01"},
        {"source": "Poll A", "date": "2026-01-01"},
    ]


def test_apply_meta_patch_ignores_non_list_polling():
    race_json = {"polling": [{"source": "A", "date": "1"}]}
    _apply_meta_patch(race_json, {"polling": "not-a-list"}, _log())
    assert race_json["polling"] == [{"source": "A", "date": "1"}]


def test_apply_meta_patch_sets_polling_note():
    race_json = {}
    _apply_meta_patch(race_json, {"polling_note": "No recent polls available."}, _log())
    assert race_json["polling_note"] == "No recent polls available."


def test_apply_meta_patch_updates_matching_candidates_by_name():
    race_json = {
        "candidates": [
            {"name": "Jane Doe", "summary": "old summary"},
            {"name": "John Smith", "summary": "unchanged"},
        ]
    }
    patch = {
        "candidates": [
            {"name": "Jane Doe", "summary": "new summary", "donor_summary": "raised $1M", "donor_sources": [{"url": "x"}]},
        ]
    }
    _apply_meta_patch(race_json, patch, _log())

    jane = race_json["candidates"][0]
    assert jane["summary"] == "new summary"
    assert jane["donor_summary"] == "raised $1M"
    assert jane["donor_sources"] == [{"url": "x"}]
    assert race_json["candidates"][1]["summary"] == "unchanged"


def test_apply_meta_patch_skips_candidates_without_match_or_name():
    race_json = {"candidates": [{"name": "Jane Doe", "summary": "unchanged"}]}
    patch = {"candidates": [{"summary": "no name here"}, {"name": "Someone Else", "summary": "no match"}]}
    _apply_meta_patch(race_json, patch, _log())
    assert race_json["candidates"][0]["summary"] == "unchanged"


def test_apply_meta_patch_ignores_non_list_donor_sources_field():
    race_json = {"candidates": [{"name": "Jane Doe", "donor_sources": [{"url": "keep"}]}]}
    patch = {"candidates": [{"name": "Jane Doe", "donor_sources": "not-a-list"}]}
    _apply_meta_patch(race_json, patch, _log())
    assert race_json["candidates"][0]["donor_sources"] == [{"url": "keep"}]


# ---------------------------------------------------------------------------
# _apply_issue_patch
# ---------------------------------------------------------------------------


def test_apply_issue_patch_merges_issues_for_matching_candidates():
    race_json = {"candidates": [{"name": "Jane Doe", "issues": {"Economy": {"stance": "old"}}}]}
    patch = {"Jane Doe": {"Healthcare": {"stance": "Supports universal coverage", "confidence": "high"}}}

    _apply_issue_patch(race_json, patch, _log())

    issues = race_json["candidates"][0]["issues"]
    assert issues["Economy"] == {"stance": "old"}
    assert issues["Healthcare"]["stance"] == "Supports universal coverage"


def test_apply_issue_patch_creates_issues_dict_when_absent():
    race_json = {"candidates": [{"name": "Jane Doe"}]}
    _apply_issue_patch(race_json, {"Jane Doe": {"Economy": {"stance": "x"}}}, _log())
    assert race_json["candidates"][0]["issues"]["Economy"]["stance"] == "x"


def test_apply_issue_patch_skips_unknown_candidate_and_non_dict_value():
    race_json = {"candidates": [{"name": "Jane Doe", "issues": {}}]}
    patch = {"Unknown Person": {"Economy": {"stance": "x"}}, "Jane Doe": "not-a-dict"}

    _apply_issue_patch(race_json, patch, _log())

    assert race_json["candidates"][0]["issues"] == {}


# ---------------------------------------------------------------------------
# _summarize_existing_stances
# ---------------------------------------------------------------------------


def test_summarize_existing_stances_formats_present_and_missing():
    candidates = [
        {
            "name": "Jane Doe",
            "issues": {"Healthcare": {"stance": "Supports universal coverage.", "confidence": "high"}},
        }
    ]
    summary = _summarize_existing_stances(candidates, ["Healthcare", "Economy"])

    assert "Jane Doe / Healthcare [high]: Supports universal coverage." in summary
    assert "Jane Doe / Economy: MISSING" in summary


def test_summarize_existing_stances_defaults_confidence_when_absent():
    candidates = [{"name": "Jane Doe", "issues": {"Healthcare": {"stance": "some stance"}}}]
    summary = _summarize_existing_stances(candidates, ["Healthcare"])
    assert "[low]" in summary


def test_summarize_existing_stances_empty_candidates_returns_placeholder():
    assert _summarize_existing_stances([], []) == "  (no existing stances)"


# ---------------------------------------------------------------------------
# _apply_candidate_patch
# ---------------------------------------------------------------------------


def test_apply_candidate_patch_updates_simple_fields():
    candidate = {"name": "Jane Doe", "summary": "old"}
    patch = {"summary": "new", "party": "Independent", "incumbent": True}

    _apply_candidate_patch(candidate, patch, _log())

    assert candidate["summary"] == "new"
    assert candidate["party"] == "Independent"
    assert candidate["incumbent"] is True


def test_apply_candidate_patch_replaces_list_fields_only_when_non_empty():
    candidate = {"name": "Jane Doe", "education": [{"school": "Old U"}]}
    patch = {"education": [], "career_history": [{"role": "Senator"}]}

    _apply_candidate_patch(candidate, patch, _log())

    # empty list must NOT overwrite existing education
    assert candidate["education"] == [{"school": "Old U"}]
    assert candidate["career_history"] == [{"role": "Senator"}]


def test_apply_candidate_patch_appends_new_links_without_duplicating():
    candidate = {"name": "Jane Doe", "links": [{"url": "https://a.com"}]}
    patch = {"links": [{"url": "https://a.com"}, {"url": "https://b.com"}]}

    _apply_candidate_patch(candidate, patch, _log())

    urls = [lnk["url"] for lnk in candidate["links"]]
    assert urls == ["https://a.com", "https://b.com"]


def test_apply_candidate_patch_merges_issues_dict():
    candidate = {"name": "Jane Doe", "issues": {"Economy": {"stance": "old"}}}
    patch = {"issues": {"Healthcare": {"stance": "new"}}}

    _apply_candidate_patch(candidate, patch, _log())

    assert candidate["issues"]["Economy"]["stance"] == "old"
    assert candidate["issues"]["Healthcare"]["stance"] == "new"


def test_apply_candidate_patch_ignores_empty_issues_dict():
    candidate = {"name": "Jane Doe", "issues": {"Economy": {"stance": "old"}}}
    _apply_candidate_patch(candidate, {"issues": {}}, _log())
    assert candidate["issues"] == {"Economy": {"stance": "old"}}


# ---------------------------------------------------------------------------
# _apply_refine_patch
# ---------------------------------------------------------------------------


def test_apply_refine_patch_applies_meta_and_candidate_patches():
    race_json = {
        "description": "old",
        "candidates": [{"name": "Jane Doe", "summary": "old summary"}],
    }
    meta_patch = {"description": "new description", "polling": [{"source": "A", "date": "1"}]}
    candidate_patches = [{"name": "Jane Doe", "summary": "new summary", "iteration_notes": ["fixed typo"]}]
    iteration_notes: list = []

    _apply_refine_patch(race_json, meta_patch, candidate_patches, _log(), iteration_notes)

    assert race_json["description"] == "new description"
    assert race_json["polling"] == [{"source": "A", "date": "1"}]
    assert race_json["candidates"][0]["summary"] == "new summary"
    assert iteration_notes == ["fixed typo"]


def test_apply_refine_patch_skips_candidate_patches_with_no_name_or_no_match():
    race_json = {"candidates": [{"name": "Jane Doe", "summary": "unchanged"}]}
    candidate_patches = [{"summary": "no name"}, {"name": "Nobody", "summary": "no match"}]

    _apply_refine_patch(race_json, {}, candidate_patches, _log(), [])

    assert race_json["candidates"][0]["summary"] == "unchanged"


def test_apply_refine_patch_ignores_empty_meta_fields():
    race_json = {"description": "old", "polling": [{"source": "A", "date": "1"}]}

    _apply_refine_patch(race_json, {"description": "", "polling": []}, [], _log(), [])

    assert race_json["description"] == "old"
    assert race_json["polling"] == [{"source": "A", "date": "1"}]


# ---------------------------------------------------------------------------
# _apply_finance_patch
# ---------------------------------------------------------------------------


def test_apply_finance_patch_updates_donor_and_voting_fields():
    race_json = {"candidates": [{"name": "Jane Doe", "links": []}]}
    patch = {
        "Jane Doe": {
            "donor_summary": "Raised $2M mostly from small donors.",
            "donor_source_url": "https://fec.gov/x",
            "donor_sources": [{"url": "https://fec.gov/x"}],
            "voting_summary": "Voted yes on X.",
            "voting_source_url": "https://congress.gov/y",
            "links": [{"url": "https://fec.gov/x"}, {"url": "https://new-link.com"}],
        }
    }

    _apply_finance_patch(race_json, patch, _log())

    candidate = race_json["candidates"][0]
    assert candidate["donor_summary"] == "Raised $2M mostly from small donors."
    assert candidate["donor_source_url"] == "https://fec.gov/x"
    assert candidate["donor_sources"] == [{"url": "https://fec.gov/x"}]
    assert candidate["voting_summary"] == "Voted yes on X."
    assert candidate["voting_source_url"] == "https://congress.gov/y"
    urls = {lnk["url"] for lnk in candidate["links"]}
    assert urls == {"https://fec.gov/x", "https://new-link.com"}


def test_apply_finance_patch_skips_unknown_candidate_and_non_dict_entries():
    race_json = {"candidates": [{"name": "Jane Doe"}]}
    patch = {"Unknown": {"donor_summary": "x"}, "Jane Doe": "not-a-dict"}

    _apply_finance_patch(race_json, patch, _log())

    assert "donor_summary" not in race_json["candidates"][0]


def test_apply_finance_patch_ignores_falsy_string_fields():
    race_json = {"candidates": [{"name": "Jane Doe", "donor_summary": "existing"}]}
    patch = {"Jane Doe": {"donor_summary": "", "voting_summary": None}}

    _apply_finance_patch(race_json, patch, _log())

    assert race_json["candidates"][0]["donor_summary"] == "existing"
    assert "voting_summary" not in race_json["candidates"][0]
