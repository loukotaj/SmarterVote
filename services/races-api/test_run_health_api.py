"""Tests for run_health serialization/backward-compat in the runs API router.

Exercises `routers/runs.py` directly (bypassing FastAPI's routing/auth layer,
since these are plain async functions) so we don't need a full TestClient +
Firestore stack just to verify the run_health default-filling behavior.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routers.runs as runs_router  # noqa: E402

# ---------------------------------------------------------------------------
# Pure helper: _ensure_run_health_default
# ---------------------------------------------------------------------------


def test_ensure_run_health_default_fills_missing_field_for_terminal_run():
    """A legacy completed run with no run_health key gets an explicit 'unknown' verdict."""
    run = {"run_id": "r1", "status": "completed"}
    result = runs_router._ensure_run_health_default(run)
    assert result["run_health"]["status"] == "unknown"
    assert result["run_health"]["reasons"] == []
    assert result["run_health"]["step_failures"] == []
    assert "predates" in (result["run_health"]["summary"] or "")


def test_ensure_run_health_default_no_summary_note_for_in_flight_run():
    """An active (pending/running) run without run_health yet is not implied to be legacy."""
    run = {"run_id": "r2", "status": "running"}
    result = runs_router._ensure_run_health_default(run)
    assert result["run_health"]["status"] == "unknown"
    assert result["run_health"]["summary"] is None


def test_ensure_run_health_default_preserves_existing_verdict():
    """A run that already has a real run_health verdict is passed through untouched."""
    run = {
        "run_id": "r3",
        "status": "completed",
        "run_health": {
            "status": "failed",
            "reasons": ["validation_failed"],
            "step_failures": [{"step": "review", "reason": "validation_failed", "detail": None}],
            "summary": "review/validation did not pass (grade=F)",
        },
    }
    result = runs_router._ensure_run_health_default(run)
    assert result["run_health"]["status"] == "failed"
    assert result["run_health"]["reasons"] == ["validation_failed"]


def test_ensure_run_health_default_treats_non_dict_value_as_missing():
    """Defensive: a corrupt non-dict run_health value is replaced, not left broken."""
    run = {"run_id": "r4", "status": "completed", "run_health": "not-a-dict"}
    result = runs_router._ensure_run_health_default(run)
    assert isinstance(result["run_health"], dict)
    assert result["run_health"]["status"] == "unknown"


# ---------------------------------------------------------------------------
# get_run() endpoint: default-filling applied end-to-end
# ---------------------------------------------------------------------------


class _FakeDoc:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, data):
        self._doc = _FakeDoc(data)

    def get(self):
        return self._doc


class _FakeCollection:
    def __init__(self, docs_by_id):
        self._docs_by_id = docs_by_id

    def document(self, doc_id):
        return _FakeDocRef(self._docs_by_id.get(doc_id))


class _FakeDb:
    def __init__(self, docs_by_id):
        self._docs_by_id = docs_by_id

    def collection(self, name):
        assert name == "pipeline_runs"
        return _FakeCollection(self._docs_by_id)


def test_get_run_endpoint_defaults_run_health_for_legacy_doc(monkeypatch):
    """A legacy run doc predating run_health tracking still serializes cleanly."""
    fake_db = _FakeDb(
        {
            "run-legacy": {
                "run_id": "run-legacy",
                "status": "completed",
                "race_id": "ga-senate-2026",
                "started_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:10:00+00:00",
            }
        }
    )
    monkeypatch.setattr(runs_router.firestore_helpers, "_get_fs", lambda: fake_db)

    result = runs_router.get_run("run-legacy")

    assert result["run_health"] == {
        "status": "unknown",
        "reasons": [],
        "step_failures": [],
        "summary": "Run predates health-verdict tracking",
    }
    # Backward compat: reading a doc that never had run_health must not crash.
    assert result["status"] == "completed"


def test_get_run_endpoint_surfaces_real_run_health(monkeypatch):
    """A run with a computed run_health verdict surfaces it unchanged through the API."""
    fake_db = _FakeDb(
        {
            "run-new": {
                "run_id": "run-new",
                "status": "completed",
                "race_id": "tx-senate-2026",
                "started_at": "2026-01-01T00:00:00+00:00",
                "run_health": {
                    "status": "degraded",
                    "reasons": ["step_no_data"],
                    "step_failures": [
                        {
                            "step": "finance",
                            "reason": "step_no_data",
                            "detail": "no candidate has donor_summary or voting_summary after the finance step",
                        }
                    ],
                    "summary": "finance: step_no_data (...)",
                },
            }
        }
    )
    monkeypatch.setattr(runs_router.firestore_helpers, "_get_fs", lambda: fake_db)

    result = runs_router.get_run("run-new")

    assert result["run_health"]["status"] == "degraded"
    assert result["run_health"]["reasons"] == ["step_no_data"]
    assert result["run_health"]["step_failures"][0]["step"] == "finance"


@pytest.mark.asyncio
async def test_get_run_endpoint_404_for_missing_run(monkeypatch):
    fake_db = _FakeDb({})
    monkeypatch.setattr(runs_router.firestore_helpers, "_get_fs", lambda: fake_db)

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await runs_router.get_run("does-not-exist")
