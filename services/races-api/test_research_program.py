from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from request_models import ResearchCheckpointRequest
from routers.research_program import (
    _cost_by_race,
    assert_race_admitted,
    get_research_program_status,
    record_research_checkpoint,
)


class _Doc:
    def __init__(self, doc_id: str, data: dict | None = None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.set_calls = []

    def to_dict(self):
        return self._data

    def get(self):
        return self

    def set(self, data, merge=False):
        self._data = data
        self.exists = True
        self.set_calls.append((data, merge))


class _Collection:
    def __init__(self, docs: dict[str, _Doc] | None = None):
        self.docs = docs or {}

    def document(self, doc_id: str):
        return self.docs.setdefault(doc_id, _Doc(doc_id))

    def limit(self, _limit: int):
        return self

    def stream(self):
        return iter(self.docs.values())


class _Db:
    def __init__(self, races: dict[str, _Doc] | None = None, checkpoints: dict[str, _Doc] | None = None):
        self.races = _Collection(races)
        self.checkpoints = _Collection(checkpoints)

    def collection(self, name: str):
        if name == "races":
            return self.races
        if name == "research_checkpoints":
            return self.checkpoints
        raise AssertionError(f"unexpected collection: {name}")


def _stable_payload() -> ResearchCheckpointRequest:
    return ResearchCheckpointRequest(
        result_state="stable",
        official_result_url="https://results.elections.myflorida.com/",
        first_checked_at="2026-08-18T18:00:00Z",
        second_checked_at="2026-08-19T00:00:00Z",
        advancing_names=["Candidate B", "Candidate A"],
        event_type="regular_primary",
        event_date="2026-08-18",
        operator="operator@example.com",
    )


def test_stable_checkpoint_requires_six_hours_between_checks():
    with pytest.raises(ValidationError, match="six hours"):
        ResearchCheckpointRequest(
            result_state="stable",
            official_result_url="https://example.gov/results",
            first_checked_at="2026-08-18T18:00:00Z",
            second_checked_at="2026-08-18T23:59:59Z",
            advancing_names=["Candidate A"],
            event_type="regular_primary",
            event_date="2026-08-18",
            operator="operator@example.com",
        )


def test_stable_checkpoint_rejects_mixed_timezone_timestamps_cleanly():
    with pytest.raises(ValidationError, match="timezone offset"):
        ResearchCheckpointRequest(
            result_state="stable",
            official_result_url="https://example.gov/results",
            first_checked_at="2026-08-18T18:00:00",
            second_checked_at="2026-08-19T00:00:00Z",
            advancing_names=["Candidate A"],
            event_type="regular_primary",
            event_date="2026-08-18",
            operator="operator@example.com",
        )


def test_admission_rejects_verified_excluded_race():
    with pytest.raises(HTTPException) as exc:
        assert_race_admitted(_Db(), "ut-senate-2026", "queue")
    assert exc.value.status_code == 409
    assert "Class III" in exc.value.detail


def test_admission_does_not_let_override_reenable_known_exclusion():
    checkpoint = _Doc(
        "ut-senate-2026",
        {
            "coverage_override": {
                "active": True,
                "official_source_url": "https://vote.utah.gov/",
                "reason": "Attempted override of audited exclusion",
                "approved_by": "operator@example.com",
            }
        },
    )

    with pytest.raises(HTTPException, match="Class III"):
        assert_race_admitted(_Db(checkpoints={checkpoint.id: checkpoint}), checkpoint.id, "publish")


def test_admission_rejects_unknown_race_without_override():
    with pytest.raises(HTTPException) as exc:
        assert_race_admitted(_Db(), "tx-special-senate-2026", "queue")

    assert exc.value.status_code == 409
    assert "coverage override" in exc.value.detail


def test_admission_accepts_sourced_override():
    checkpoint = _Doc(
        "tx-special-senate-2026",
        {
            "race_id": "tx-special-senate-2026",
            "coverage_override": {
                "active": True,
                "official_source_url": "https://www.sos.texas.gov/elections/",
                "reason": "Officially scheduled special election",
                "approved_by": "operator@example.com",
            },
        },
    )
    db = _Db(checkpoints={checkpoint.id: checkpoint})

    result = assert_race_admitted(db, checkpoint.id, "queue")

    assert result["source"] == "coverage_override"


def test_checkpoint_write_computes_stable_fingerprint():
    db = _Db()
    with patch("firestore_helpers._get_fs", return_value=db):
        result = record_research_checkpoint("fl-house-13-2026", _stable_payload())

    assert result["result_state"] == "stable"
    assert len(result["result_fingerprint"]) == 64
    stored, merge = db.checkpoints.document("fl-house-13-2026").set_calls[0]
    assert merge is False
    assert stored["result_fingerprint"] == result["result_fingerprint"]


def test_cost_join_uses_run_workflow_and_metric_cost():
    with patch(
        "routers.pipeline._load_summary_firestore_records",
        return_value=(
            {"run-1": {"run_id": "run-1", "race_id": "fl-house-13-2026", "workflow": "unknown", "cost_usd": 0.24}},
            {
                "run-1": {
                    "run_id": "run-1",
                    "race_id": "fl-house-13-2026",
                    "workflow": "discovery",
                    "enabled_steps": ["discovery"],
                }
            },
            True,
            True,
        ),
    ):
        by_race, by_workflow = _cost_by_race(MagicMock())

    assert by_race["fl-house-13-2026"]["by_workflow"] == {"discovery": 0.24}
    assert by_workflow == {"discovery": 0.24}


def test_status_exposes_published_stage_with_provenance():
    race = _Doc(
        "fl-house-13-2026",
        {
            "race_id": "fl-house-13-2026",
            "status": "published",
            "published_at": "2026-08-18T00:00:00Z",
            "published_updated_utc": "2026-08-18T00:00:00Z",
            "published_contest_stage": "post_primary_general",
            "published_candidate_count": 2,
            "published_catalog_health": {"missing_issue_count": 24},
        },
    )
    db = _Db(races={race.id: race})
    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch(
            "routers.research_program._cost_by_race",
            return_value=(
                {
                    race.id: {
                        "run_count": 2,
                        "total_usd": 0.31,
                        "by_workflow": {"discovery": 0.09, "issues": 0.22},
                        "last_run_at": "2026-08-18T00:00:00Z",
                    }
                },
                {"discovery": 0.09, "issues": 0.22},
            ),
        ),
    ):
        result = get_research_program_status(include_rows=True)

    assert result["summary"]["coverage_count"] == 507
    row = next(row for row in result["rows"] if row["race_id"] == race.id)
    assert row["published"]["source"] == "published"
    assert row["published"]["contest_stage"] == "post_primary_general"
    assert row["latest_source"] == "published"
    assert row["cost"]["by_workflow"] == {"discovery": 0.09, "issues": 0.22}
    assert result["summary"]["workflow_spend_usd"] == {"discovery": 0.09, "issues": 0.22}


def test_status_does_not_classify_chamber_forecasts_as_an_orphaned_race():
    aggregate = _Doc("chamber_forecasts", {"race_id": "chamber_forecasts", "status": "published"})
    db = _Db(races={aggregate.id: aggregate})

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("routers.research_program._cost_by_race", return_value=({}, {})),
    ):
        result = get_research_program_status(include_rows=False)

    assert result["summary"]["orphaned_catalog_count"] == 0
    assert result["orphaned_catalog_race_ids"] == []
