"""Tests for the hourly community race-issue triage script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "triage_race_issues.py"
_spec = importlib.util.spec_from_file_location("triage_race_issues", MODULE_PATH)
triage = importlib.util.module_from_spec(_spec)
sys.modules["triage_race_issues"] = triage
_spec.loader.exec_module(triage)


ISSUE_BODY = """### Race ID

nj-senate-2026

### Candidate Name

Veronica Fernandez

### What type of data is missing?

- [x] Issue stances / positions
- [ ] Donor information
- [ ] Voting record
- [x] Biographical information
- [x] Campaign website
- [ ] Other

### Source URL(s)

https://veronicaforsenate.com/

### Additional Context

_No response_
"""


class TestExtractField:
    def test_reads_a_simple_field(self):
        assert triage.extract_field(ISSUE_BODY, "Race ID") == "nj-senate-2026"
        assert triage.extract_field(ISSUE_BODY, "Candidate Name") == "Veronica Fernandez"

    def test_treats_no_response_placeholder_as_empty(self):
        assert triage.extract_field(ISSUE_BODY, "Additional Context") == ""

    def test_missing_field_is_empty(self):
        assert triage.extract_field(ISSUE_BODY, "Nonexistent") == ""


class TestResolveRaceId:
    def test_extracts_and_normalizes(self):
        assert triage.resolve_race_id({"body": ISSUE_BODY}) == "nj-senate-2026"

    def test_accepts_race_request_proposed_label(self):
        body = "### Proposed Race ID\n\ntx-governor-2026\n\n### Office\n\nGovernor\n"
        assert triage.resolve_race_id({"body": body}) == "tx-governor-2026"

    def test_rejects_missing_race_id(self):
        with pytest.raises(triage.TriageError):
            triage.resolve_race_id({"body": "### Candidate Name\n\nJane Smith\n"})

    def test_rejects_malformed_race_id(self):
        body = "### Race ID\n\nNot A Race ID!\n"
        with pytest.raises(triage.TriageError):
            triage.resolve_race_id({"body": body})


class TestFindCandidate:
    record = {
        "candidates": [
            {"name": "Cory Booker", "party": "Democratic", "image_url": "https://example.test/booker.jpg"},
            {"name": "Verónica Fernández", "party": "Unknown", "image_url": None},
        ]
    }

    def test_matches_ignoring_accents(self):
        found = triage.find_candidate(self.record, "Veronica Fernandez")
        assert found is not None and found["party"] == "Unknown"

    def test_matches_surname_with_suffix(self):
        found = triage.find_candidate({"candidates": [{"name": "Bob Casey"}]}, "Bob Casey Jr.")
        assert found is not None

    def test_returns_none_for_absent_candidate(self):
        assert triage.find_candidate(self.record, "Someone Else") is None

    def test_returns_none_for_blank_name(self):
        assert triage.find_candidate(self.record, "") is None


class TestReportedConcerns:
    def test_reads_only_checked_boxes(self):
        assert triage.reported_concerns(ISSUE_BODY) == {"issues", "roster"}

    def test_no_checkboxes_yields_nothing(self):
        assert triage.reported_concerns("### Race ID\n\nmi-senate-2026\n") == set()


class TestRecommend:
    def test_roster_verification_leads_when_unverified(self):
        actions = triage.recommend({"issues"}, roster_unverified=True, has_draft=False)
        assert actions[0]["steps"] == ["discovery"]
        assert actions[0]["baseline"] == "published"

    def test_issues_never_queued_alone(self):
        actions = triage.recommend({"issues"}, roster_unverified=False, has_draft=False)
        assert actions[0]["steps"] == triage.COMBINED_STEPS
        assert "review" in actions[0]["steps"] and "iteration" in actions[0]["steps"]

    def test_existing_draft_builds_on_latest(self):
        actions = triage.recommend({"finance"}, roster_unverified=False, has_draft=True)
        assert actions[0]["baseline"] == "latest"

    def test_roster_only_concern_uses_discovery(self):
        actions = triage.recommend({"roster"}, roster_unverified=False, has_draft=False)
        assert actions[0]["steps"] == ["discovery"]

    def test_cheap_concerns_do_not_trigger_issue_research(self):
        actions = triage.recommend({"images", "forecast"}, roster_unverified=False, has_draft=False)
        assert all("issues" not in action["steps"] for action in actions)
        assert [action["steps"] for action in actions] == [["forecast"], ["images"]]

    def test_no_concerns_yields_no_actions(self):
        assert triage.recommend(set(), roster_unverified=False, has_draft=False) == []


class TestIsRaceIssue:
    def test_matches_by_title_prefix_when_labels_missing(self):
        issue = {"title": "[Data] Missing data for: Jane Smith", "labels": []}
        assert triage.is_race_issue(issue)

    def test_matches_by_label(self):
        issue = {"title": "Something else", "labels": [{"name": "race-request"}]}
        assert triage.is_race_issue(issue)

    def test_ignores_unrelated_issues(self):
        assert not triage.is_race_issue({"title": "Fix CI", "labels": [{"name": "bug"}]})


class TestBuildTriageComment:
    def test_uncatalogued_race_on_data_report_is_flagged(self):
        issue = {"title": "[Data] Missing data for: Jane Smith", "body": ISSUE_BODY}
        comment = triage.build_triage_comment(issue, "zz-senate-2026", None)
        assert "not in catalog" in comment
        assert "@loukotaj" in comment

    def test_uncatalogued_race_on_request_is_expected(self):
        issue = {"title": "[Race Request] tx-governor-2026", "body": ISSUE_BODY}
        comment = triage.build_triage_comment(issue, "tx-governor-2026", None)
        assert "new race request" in comment

    def test_candidate_in_roster_with_existing_draft(self):
        record = {
            "title": "2026 U.S. Senate Election in New Jersey",
            "status": "published",
            "quality_grade": "A",
            "candidate_count": 7,
            "draft_exists": True,
            "candidates": [{"name": "Veronica Fernandez", "party": "Democratic", "image_url": "https://example.com/img.jpg"}],
            "catalog_health": {
                "gaps": ["missing_issue_research"],
            },
        }
        issue = {"title": "[Data] Missing data for: Veronica Fernandez", "body": ISSUE_BODY}
        comment = triage.build_triage_comment(issue, "nj-senate-2026", record)

        assert "A run has been completed and is pending review." in comment
        assert 'queue_races(race_ids=["nj-senate-2026"]' in comment
        assert "@loukotaj" in comment
