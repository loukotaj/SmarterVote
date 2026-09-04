"""Refinement patches must not create or strip down to unsourced assertions."""

from pipeline_client.agent.patches import _merge_issue_data

SOURCE = {"url": "https://example.com/policy", "type": "website", "last_accessed": "2026-09-02T00:00:00Z"}


def test_a_new_unsourced_substantive_stance_is_refused():
    """32 of 69 unsourced stances in the catalogue have no research_audit at all.

    They never came from the issues phase; they were written straight in by a
    patch, which bypassed the guard `set_issue_stance` enforces.
    """
    incoming = {
        "issue": "Foreign Policy",
        "stance": "McKay criticised the incumbent in a campaign video.",
        "confidence": "medium",
        "sources": [],
    }

    assert _merge_issue_data(None, incoming) is None


def test_a_new_sourced_stance_is_accepted():
    incoming = {
        "issue": "Foreign Policy",
        "stance": "Supports continued security assistance.",
        "confidence": "high",
        "sources": [SOURCE],
    }

    assert _merge_issue_data(None, incoming) == incoming


def test_a_new_documented_absence_is_accepted_without_sources():
    incoming = {"issue": "Foreign Policy", "stance": "No public position found", "confidence": "low", "sources": []}

    assert _merge_issue_data(None, incoming) == incoming


def test_a_rewrite_cannot_strip_an_existing_citation():
    """An explicit empty list does not erase stored evidence — the merge keeps it.

    Worth pinning: it means a patch rewriting a stance can never leave it
    unsourced, so the 37 catalogue stances that lost their sources were not lost
    here.
    """
    existing = {
        "issue": "Foreign Policy",
        "stance": "Supports continued security assistance.",
        "confidence": "high",
        "sources": [SOURCE],
    }
    incoming = {"stance": "Now says something sharper about a named opponent.", "sources": []}

    merged = _merge_issue_data(existing, incoming)

    assert merged["sources"] == [SOURCE]
    assert merged["stance"] == "Now says something sharper about a named opponent."


def test_a_rewrite_keeps_existing_sources_when_the_patch_omits_them():
    existing = {"issue": "Foreign Policy", "stance": "Old wording.", "confidence": "high", "sources": [SOURCE]}
    incoming = {"stance": "Clearer wording, same claim."}

    merged = _merge_issue_data(existing, incoming)

    assert merged["stance"] == "Clearer wording, same claim."
    assert merged["sources"] == [SOURCE]


def test_a_rewrite_to_a_documented_absence_may_drop_sources():
    existing = {"issue": "Foreign Policy", "stance": "Old claim.", "confidence": "high", "sources": [SOURCE]}
    incoming = {"stance": "No public position found", "confidence": "low", "sources": []}

    merged = _merge_issue_data(existing, incoming)

    assert merged["stance"] == "No public position found"
