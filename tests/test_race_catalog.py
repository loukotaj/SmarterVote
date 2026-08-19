"""Behavioral tests for shared.race_catalog helper functions."""

from datetime import datetime, timedelta, timezone

from shared.models import CanonicalIssue
from shared.race_catalog import (
    _coerce_datetime,
    _strong_roster_source,
    build_agent_metrics_summary,
    build_candidate_summaries,
    build_catalog_health,
    build_forecast_summary,
    build_race_summary_fields,
    build_versioned_catalog_fields,
    compute_freshness,
    extract_quality_grade,
)


def test_coerce_datetime_passes_through_aware_datetime():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _coerce_datetime(aware) is aware


def test_coerce_datetime_adds_utc_to_naive_datetime():
    naive = datetime(2026, 1, 1)
    result = _coerce_datetime(naive)
    assert result.tzinfo == timezone.utc


def test_coerce_datetime_parses_z_suffixed_string():
    result = _coerce_datetime("2026-01-01T00:00:00Z")
    assert result == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_coerce_datetime_none_returns_none():
    assert _coerce_datetime(None) is None


def test_coerce_datetime_blank_string_returns_none():
    assert _coerce_datetime("   ") is None


def test_coerce_datetime_invalid_string_returns_none():
    assert _coerce_datetime("not-a-date") is None


def test_coerce_datetime_unsupported_type_returns_none():
    assert _coerce_datetime(12345) is None


def test_compute_freshness_none_updated_returns_none():
    assert compute_freshness(None) is None


def test_compute_freshness_recent():
    now = datetime.now(timezone.utc).isoformat()
    assert compute_freshness(now) == "recent"


def test_compute_freshness_stale_for_middling_date(monkeypatch):
    monkeypatch.delenv("PIPELINE_FRESHNESS_AGING_DAYS", raising=False)
    monkeypatch.delenv("PIPELINE_FRESHNESS_STALE_DAYS", raising=False)
    middling = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    assert compute_freshness(middling) == "stale"


def test_compute_freshness_old_for_very_stale_date():
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    assert compute_freshness(old) == "old"


def test_extract_quality_grade_missing_validation_grade_returns_none():
    assert extract_quality_grade({}) is None


def test_extract_quality_grade_non_dict_validation_grade_returns_none():
    assert extract_quality_grade({"validation_grade": "not-a-dict"}) is None


def test_extract_quality_grade_returns_grade_string():
    assert extract_quality_grade({"validation_grade": {"grade": "A"}}) == "A"


def test_extract_quality_grade_falsy_grade_returns_none():
    assert extract_quality_grade({"validation_grade": {"grade": None}}) is None


def test_build_candidate_summaries_filters_non_dict_entries():
    race_data = {
        "candidates": [
            {"name": "Jane Doe", "party": "Independent", "incumbent": True, "image_url": "http://x/y.png"},
            "not-a-candidate",
            {"name": "John Smith"},
        ]
    }

    summaries = build_candidate_summaries(race_data)

    assert summaries == [
        {"name": "Jane Doe", "party": "Independent", "incumbent": True, "image_url": "http://x/y.png"},
        {"name": "John Smith", "party": None, "incumbent": False, "image_url": None},
    ]


def test_build_candidate_summaries_missing_or_non_list_candidates_returns_empty():
    assert build_candidate_summaries({}) == []
    assert build_candidate_summaries({"candidates": "not-a-list"}) == []


def test_build_agent_metrics_summary_missing_returns_none():
    assert build_agent_metrics_summary({}) is None
    assert build_agent_metrics_summary({"agent_metrics": "nope"}) is None


def test_build_agent_metrics_summary_extracts_expected_fields():
    race_data = {"agent_metrics": {"estimated_usd": 1.23, "model": "gpt-4o", "total_tokens": 500, "extra": "ignored"}}

    assert build_agent_metrics_summary(race_data) == {
        "estimated_usd": 1.23,
        "model": "gpt-4o",
        "total_tokens": 500,
    }


def test_build_forecast_summary_missing_returns_none():
    assert build_forecast_summary({}) is None


def test_build_forecast_summary_defaults_missing_list_fields_to_empty():
    race_data = {"forecast": {"predicted_winner_name": "Jane Doe"}}

    summary = build_forecast_summary(race_data)

    assert summary["predicted_winner_name"] == "Jane Doe"
    assert summary["party_probabilities"] == {}
    assert summary["key_reasons"] == []
    assert summary["source_urls"] == []
    assert summary["market_signals"] == []
    assert summary["based_on_poll_count"] == 0


def test_build_catalog_health_distinguishes_discovery_partial_and_terminal_results():
    discovery = build_catalog_health({"candidates": [{"name": "A", "issues": {}}]})
    assert discovery["research_tier"] == "discovery_only"
    assert discovery["missing_issue_count"] == 12
    assert "missing_issue_research" in discovery["gaps"]

    issues = {
        issue.value: {
            "stance": (
                "No public position found after repeated research attempts." if index == 0 else "Supports this policy."
            ),
            "sources": [] if index == 0 else [{"url": "https://example.com"}],
        }
        for index, issue in enumerate(CanonicalIssue)
    }
    complete = build_catalog_health(
        {
            "candidates": [
                {
                    "name": "A",
                    "image_url": "https://example.com/a.jpg",
                    "roster_sources": [{"url": "https://elections.example.gov"}],
                    "issues": issues,
                    "donor_summary": "No federal filings yet.",
                    "donor_source_url": "https://fec.gov",
                }
            ],
            "forecast": {"rating": "tossup", "source_urls": ["https://cookpolitical.com"]},
        }
    )
    assert complete["research_tier"] == "full_unreviewed"
    assert complete["terminal_issue_count"] == 12
    assert complete["substantive_issue_count"] == 11
    assert complete["no_position_issue_count"] == 1
    assert complete["sourced_issue_count"] == 11
    assert complete["forecast_evidence_complete"] is True


def test_build_catalog_health_marks_passing_grade_as_validated():
    health = build_catalog_health(
        {
            "candidates": [{"name": "A"}],
            "validation_grade": {"grade": "A", "passed": True},
        }
    )
    assert health["research_tier"] == "validated"
    assert health["validation_passed"] is True


def test_catalog_health_tracks_strong_roster_evidence_and_section_freshness():
    health = build_catalog_health(
        {
            "race_id": "tx-house-01-2026",
            "candidates": [
                {
                    "name": "A",
                    "roster_sources": [
                        {
                            "url": "https://elections.example.gov/contest",
                            "race_id": "tx-house-01-2026",
                            "evidence_tier": 1,
                            "retrieval_status": "content",
                            "last_accessed": "2026-07-28T00:00:00Z",
                        }
                    ],
                    "issues": {},
                }
            ],
        }
    )

    assert health["roster_strong_evidence_candidates"] == 1
    assert health["section_freshness"]["roster"]["status"] == "recent"


def _race_with_roster_source(**source_extra):
    """A RaceJSON-shaped race — slug under "id", which is what production serves."""
    return {
        "id": "tx-house-01-2026",
        "candidates": [
            {
                "name": "A",
                "roster_sources": [
                    {
                        "url": "https://elections.example.gov/contest",
                        "evidence_tier": 1,
                        "retrieval_status": "content",
                        **source_extra,
                    }
                ],
                "issues": {},
            }
        ],
    }


def test_strong_roster_evidence_reads_racejson_id_not_race_id():
    """RaceJSON stores the slug as "id"; only admin records use "race_id". Reading
    the wrong key made the comparison race id None, so every source that named its
    own race_id was disqualified and this counter was structurally always 0."""
    health = build_catalog_health(_race_with_roster_source(race_id="tx-house-01-2026"))
    assert health["roster_strong_evidence_candidates"] == 1


def test_naming_the_race_id_never_weakens_a_roster_source():
    """The inversion that hid the bug: stripping race_id used to *promote* a source
    to strong. Better-formed evidence must never score worse than vaguer evidence."""
    with_id = build_catalog_health(_race_with_roster_source(race_id="tx-house-01-2026"))
    without_id = build_catalog_health(_race_with_roster_source())
    assert with_id["roster_strong_evidence_candidates"] >= without_id["roster_strong_evidence_candidates"]


def test_strong_roster_evidence_still_rejects_a_different_contest():
    """The race-id check must keep doing its actual job."""
    health = build_catalog_health(_race_with_roster_source(race_id="tx-house-99-2026"))
    assert health["roster_strong_evidence_candidates"] == 0


def test_build_race_summary_fields_uses_race_data_id_over_race_id_argument():
    race_data = {
        "id": "actual-id",
        "title": "Georgia Senate",
        "contest_stage": "post_primary_general",
        "candidates": [{"name": "A"}],
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "validation_grade": {"grade": "B"},
    }

    fields = build_race_summary_fields("fallback-id", race_data)

    assert fields["race_id"] == "actual-id"
    assert fields["candidate_count"] == 1
    assert fields["quality_grade"] == "B"
    assert fields["contest_stage"] == "post_primary_general"
    assert fields["freshness"] == "recent"
    assert fields["catalog_health"]["research_tier"] == "graded_low"


def test_build_race_summary_fields_falls_back_to_argument_race_id():
    fields = build_race_summary_fields("fallback-id", {})

    assert fields["race_id"] == "fallback-id"
    assert fields["candidate_count"] == 0
    assert fields["quality_grade"] is None
    assert fields["contest_stage"] == "unknown"
    assert fields["freshness"] is None


def test_build_versioned_catalog_fields_prefixes_keys():
    race_data = {
        "candidates": [{"name": "A"}, {"name": "B"}],
        "updated_utc": "2026-01-01T00:00:00Z",
        "contest_stage": "pre_primary",
        "validation_grade": {"grade": "A"},
    }

    fields = build_versioned_catalog_fields("draft", race_data)

    assert fields == {
        "draft_updated_utc": "2026-01-01T00:00:00Z",
        "draft_contest_stage": "pre_primary",
        "draft_candidate_count": 2,
        "draft_quality_grade": "A",
        "draft_catalog_health": build_catalog_health(race_data),
    }


# ---------------------------------------------------------------------------
# `_strong_roster_source` re-derives the roster contract's tier rule
# ---------------------------------------------------------------------------


def test_strong_roster_source_agrees_with_the_roster_contract():
    """`shared.race_catalog` says a roster source is strong when
    `tier <= 2 and retrieval_status == "content"`. That is the roster contract's
    COMPLETENESS_TIERS spelled out as a literal.

    `shared` sits below `pipeline_client` and cannot import the contract, so the
    rule is written twice by necessity. This asserts the two still say the same
    thing: change the contract's tiers and the catalog's counts of
    "strong evidence" candidates silently stop matching what the tool enforces.
    """
    from pipeline_client.agent.roster_contract import COMPLETENESS_TIERS, MEMBERSHIP_TIERS

    assert max(COMPLETENESS_TIERS) == 2, "race_catalog hardcodes `tier <= 2`"
    assert min(COMPLETENESS_TIERS) >= 1
    assert all(
        tier.retrieval_status == "content" for tier in MEMBERSHIP_TIERS if tier.tier in COMPLETENESS_TIERS
    ), 'race_catalog hardcodes retrieval_status == "content" for these tiers'


def test_strong_roster_source_accepts_and_rejects_by_that_rule():
    race_id = "ga-senate-2026"
    strong = {"url": "https://sos.ga.gov/x", "evidence_tier": 1, "retrieval_status": "content", "race_id": race_id}
    assert _strong_roster_source(strong, race_id)

    # A snippet is never strong, whatever tier it claims.
    assert not _strong_roster_source({**strong, "retrieval_status": "snippet"}, race_id)
    # Tier 3 is outside the completeness tiers.
    assert not _strong_roster_source({**strong, "evidence_tier": 3}, race_id)
    # Evidence for a different contest does not support this one.
    assert not _strong_roster_source({**strong, "race_id": "az-senate-2026"}, race_id)
    # A source with no URL cannot be cited at all.
    assert not _strong_roster_source({**strong, "url": ""}, race_id)
