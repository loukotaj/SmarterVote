"""Regression coverage for evidence preservation and deterministic quality gates."""

from pipeline_client.agent.evidence import merge_source_lists, preserve_baseline_evidence
from pipeline_client.agent.handlers import _make_editing_handlers
from pipeline_client.agent.polling_quality import polling_semantic_problem
from pipeline_client.agent.review import (
    _remove_confirmed_dead_candidate_sources,
    check_profile_quality,
    compute_validation_grade,
)


def _source(url: str) -> dict:
    return {"url": url, "type": "website"}


def test_merge_source_lists_is_monotonic_and_deduplicated():
    merged = merge_source_lists(
        [_source("https://example.test/new"), _source("https://example.test/shared")],
        [_source("https://example.test/old"), _source("https://example.test/shared")],
    )

    assert [source["url"] for source in merged] == [
        "https://example.test/new",
        "https://example.test/shared",
        "https://example.test/old",
    ]


def test_preserve_baseline_evidence_restores_omitted_issue_and_profile_sources():
    baseline = {
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [_source("https://example.test/bio")],
                "issues": {"Healthcare": {"stance": "Old", "sources": [_source("https://example.test/health")]}},
            }
        ]
    }
    updated = {
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [],
                "issues": {"Healthcare": {"stance": "Updated", "confidence": "high", "sources": []}},
            }
        ]
    }

    restored = preserve_baseline_evidence(updated, baseline)

    assert restored == 2
    assert updated["candidates"][0]["summary_sources"][0]["url"] == "https://example.test/bio"
    assert updated["candidates"][0]["issues"]["Healthcare"]["sources"][0]["url"] == "https://example.test/health"


def test_explicit_source_removal_is_not_undone_by_baseline_preservation():
    dead_url = "https://example.test/dead"
    baseline = {
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [_source(dead_url)],
                "issues": {"Healthcare": {"stance": "Old", "sources": [_source(dead_url)]}},
            }
        ]
    }
    updated = {
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [_source(dead_url)],
                "issues": {"Healthcare": {"stance": "Old", "sources": [_source(dead_url)]}},
            }
        ]
    }
    handlers = _make_editing_handlers(updated, lambda *_: None)

    result = handlers["remove_candidate_source_url"]({"candidate_name": "Alice", "url": dead_url})
    preserve_baseline_evidence(updated, baseline)

    assert result.startswith("Removed 2 occurrence(s)")
    assert updated["candidates"][0]["summary_sources"] == []
    assert updated["candidates"][0]["issues"]["Healthcare"]["sources"] == []
    assert updated["pipeline_state"]["removed_source_urls"] == [{"candidate_name": "Alice", "url": dead_url}]


def test_issue_editor_preserves_existing_sources_and_rejects_new_uncited_claims():
    race = {
        "candidates": [
            {
                "name": "Alice",
                "issues": {
                    "Healthcare": {
                        "stance": "Old stance",
                        "confidence": "medium",
                        "sources": [_source("https://example.test/health")],
                    }
                },
            }
        ]
    }
    handlers = _make_editing_handlers(race, lambda *_: None)

    accepted = handlers["set_issue_stance"](
        {
            "candidate_name": "Alice",
            "issue": "Healthcare",
            "stance": "Updated stance",
            "confidence": "high",
        }
    )
    rejected = handlers["set_issue_stance"](
        {
            "candidate_name": "Alice",
            "issue": "Economy",
            "stance": "Supports a specific tax policy.",
            "confidence": "high",
        }
    )

    assert not accepted.startswith("ERROR:")
    assert race["candidates"][0]["issues"]["Healthcare"]["sources"][0]["url"] == "https://example.test/health"
    assert rejected.startswith("ERROR:")
    assert "Economy" not in race["candidates"][0]["issues"]


def test_polling_semantics_reject_placeholder_and_election_results():
    assert polling_semantic_problem({"pollster": "Example", "matchups": []})
    assert polling_semantic_problem(
        {
            "pollster": "Associated Press",
            "source_url": "https://state.example/elections/results/house-3",
            "matchups": [{"candidates": ["Alice", "Bob"], "percentages": [52, 48]}],
        }
    )
    assert (
        polling_semantic_problem(
            {
                "pollster": "Reliable Research",
                "source_url": "https://reliable.example/polls/house-3",
                "matchups": [{"candidates": ["Alice", "Bob"], "percentages": [48, 45]}],
            }
        )
        is None
    )


def test_automated_warning_caps_validation_below_passing():
    grade = compute_validation_grade(
        [
            {"model": "reviewer", "score": 96, "verdict": "approved", "flags": []},
            {
                "model": "automated-profile-quality",
                "score": None,
                "verdict": "flagged",
                "flags": [{"severity": "warning", "field": "candidate.summary_sources"}],
            },
        ]
    )

    assert grade["score"] == 79
    assert grade["grade"] == "C"
    assert grade["passed"] is False


def test_quality_check_flags_implausible_house_term_count():
    race = {
        "office": "U.S. House of Representatives",
        "election_date": "2026-11-03",
        "forecast": {"rationale": "Alice has a 14-term incumbency advantage."},
        "candidates": [
            {
                "name": "Alice",
                "incumbent": True,
                "career_history": [{"title": "U.S. Representative", "start_year": 2013}],
                "issues": {},
            }
        ],
    }

    review = check_profile_quality(race)

    assert any(flag["field"] == "forecast.rationale" and flag["severity"] == "error" for flag in review["flags"])


def test_confirmed_dead_candidate_source_is_removed_and_tombstoned():
    dead_url = "https://example.test/dead"
    race = {
        "candidates": [
            {
                "name": "Alice",
                "summary_sources": [_source(dead_url)],
                "donor_sources": [_source(dead_url)],
                "issues": {},
            }
        ]
    }
    review = {
        "flags": [
            {
                "field": "candidates[0].summary_sources[0].url",
                "concern": f"Cited source URL ({dead_url}) returned a dead link: HTTP error 404.",
                "severity": "warning",
            }
        ]
    }

    removed = _remove_confirmed_dead_candidate_sources(race, review)

    assert removed == 2
    assert race["candidates"][0]["summary_sources"] == []
    assert race["candidates"][0]["donor_sources"] == []
    assert race["pipeline_state"]["removed_source_urls"] == [{"candidate_name": "Alice", "url": dead_url}]
