"""Tests for the races-api admin endpoints added in the pipeline-client migration.

Uses FastAPI TestClient with mocked Firestore/GCS dependencies.
Auth is bypassed by patching `verify_token` to return an empty dict.
"""

import json
import os

# ---------------------------------------------------------------------------
# Ensure the races-api source directory is on sys.path so we can import `main`
# ---------------------------------------------------------------------------
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

RACES_API_DIR = pathlib.Path(__file__).parent.parent / "services" / "races-api"
if str(RACES_API_DIR) not in sys.path:
    sys.path.insert(0, str(RACES_API_DIR))

# Pre-import helper modules so patches target the correct module objects.
import firestore_helpers  # noqa: E402
import gcs_helpers  # noqa: E402


def test_pipeline_metrics_prefers_exact_provider_cost():
    from routers.pipeline import _compute_metrics_summary, _normalize_pipeline_run

    record = _normalize_pipeline_run(
        {
            "race_id": "ar-senate-2026",
            "status": "completed",
            "estimated_usd": 0.02,
            "cost_usd": 0.01234567,
            "cost_source": "provider",
            "candidate_count": 2,
            "cheap_mode": True,
        },
        "run-exact",
    )

    assert record["cost_usd"] == pytest.approx(0.01234567)
    assert record["cost_source"] == "provider"
    assert _compute_metrics_summary([record])["total_usd"] == pytest.approx(0.0123)


def test_collapse_continuation_chain_reports_one_logical_run():
    from routers.runs import _collapse_continuation_chains

    runs = [
        {
            "run_id": "run-root",
            "status": "continued",
            "started_at": "2026-06-14T20:00:00+00:00",
            "continued_at": "2026-06-14T20:08:00+00:00",
            "continuation_run_id": "run-child",
        },
        {
            "run_id": "run-child",
            "status": "completed",
            "started_at": "2026-06-14T20:08:01+00:00",
            "completed_at": "2026-06-14T20:12:00+00:00",
        },
    ]

    collapsed = _collapse_continuation_chains(runs)

    assert len(collapsed) == 1
    assert collapsed[0]["run_id"] == "run-child"
    assert collapsed[0]["logical_run_id"] == "run-root"
    assert collapsed[0]["status"] == "completed"
    assert collapsed[0]["continuation_count"] == 1
    assert collapsed[0]["duration_ms"] == 12 * 60 * 1000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient with auth disabled and mocked cloud dependencies."""
    monkeypatch.setenv("SKIP_AUTH", "true")
    monkeypatch.setenv("ADMIN_API_KEY", "test-key")

    # Patch cloud helpers at their actual module locations (routers import them there).
    with (
        patch("firestore_helpers._get_fs", side_effect=_make_mock_fs),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        import main as app_module
        from fastapi.testclient import TestClient

        # Reset the Firestore singleton so each test gets a fresh mock.
        firestore_helpers._fs_db = None
        yield TestClient(app_module.app)


# Store created per test call to make assertions possible
_fs_instances: list = []


def _make_mock_fs():
    db = _build_empty_firestore_mock()
    _fs_instances.append(db)
    return db


def _build_empty_firestore_mock() -> MagicMock:
    """Return a minimal Firestore mock that returns empty collections by default."""
    db = MagicMock()

    def _stream(*a, **kw):
        return iter([])

    def _make_coll(name):
        coll = MagicMock()
        coll.stream.return_value = iter([])
        coll.document.return_value = _make_missing_doc_ref()
        coll.order_by.return_value = coll
        coll.limit.return_value = coll
        coll.where.return_value = coll
        return coll

    db.collection.side_effect = _make_coll
    return db


def _make_missing_doc_ref() -> MagicMock:
    ref = MagicMock()
    doc = MagicMock()
    doc.exists = False
    doc.to_dict.return_value = {}
    ref.get.return_value = doc
    return ref


def _make_existing_doc(data: dict) -> MagicMock:
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = dict(data)
    return doc


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /steps
# ---------------------------------------------------------------------------


def test_list_steps(client):
    resp = client.get("/steps")
    assert resp.status_code == 200
    body = resp.json()
    assert "steps" in body
    assert "discovery" in body["steps"]
    assert body["step_details"][0] == {"id": "discovery", "label": "Discovery", "weight": 12}
    assert "polling" in body["steps"]
    assert "voter_resources" in body["steps"]


# ---------------------------------------------------------------------------
# /api/queue — GET returns empty list when Firestore is empty
# ---------------------------------------------------------------------------


def test_get_queue_empty(client):
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["pending"] == 0
    assert body["running"] is False


def test_get_queue_does_not_count_continuation_parent_as_running():
    """Continuation ancestors should not inflate active run counts."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    parent_doc = _make_existing_doc(
        {
            "id": "item-parent",
            "race_id": "az-senate-2026",
            "run_id": "run-parent",
            "status": "running",
            "created_at": "2026-05-06T00:00:00+00:00",
        }
    )
    child_doc = _make_existing_doc(
        {
            "id": "item-child",
            "race_id": "az-senate-2026",
            "run_id": "run-child",
            "status": "running",
            "parent_run_id": "run-parent",
            "is_continuation": True,
            "created_at": "2026-05-06T00:10:00+00:00",
        }
    )
    queue_coll = MagicMock()
    queue_coll.order_by.return_value = queue_coll
    queue_coll.stream.return_value = iter([parent_doc, child_doc])

    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: queue_coll if name == "pipeline_queue" else MagicMock()

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/queue")

    assert resp.status_code == 200
    body = resp.json()
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id["item-parent"]["status"] == "continued"
    assert by_id["item-child"]["status"] == "running"
    assert body["running"] is True
    assert sum(1 for item in body["items"] if item["status"] == "running") == 1


# ---------------------------------------------------------------------------
# /api/races/queue — POST queues a valid race ID
# ---------------------------------------------------------------------------


def test_get_queue_hides_active_item_when_run_is_terminal():
    """Queue listing should self-heal stale active queue items from the run record."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_queue_doc = _make_existing_doc(
        {
            "id": "item-stale",
            "race_id": "ga-senate-2026",
            "run_id": "run-completed",
            "status": "running",
            "created_at": "2026-05-15T00:18:00+00:00",
        }
    )
    stale_ref = MagicMock()

    completed_run_doc = _make_existing_doc(
        {
            "run_id": "run-completed",
            "race_id": "ga-senate-2026",
            "status": "completed",
            "completed_at": "2026-05-15T00:48:00+00:00",
        }
    )
    run_ref = MagicMock()
    run_ref.get.return_value = completed_run_doc

    queue_coll = MagicMock()
    queue_coll.order_by.return_value = queue_coll
    queue_coll.stream.return_value = iter([stale_queue_doc])
    queue_coll.document.return_value = stale_ref

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: queue_coll if name == "pipeline_queue" else runs_coll

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/queue?active_only=true")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["running"] is False
    stale_ref.update.assert_called_once_with({"status": "completed", "completed_at": "2026-05-15T00:48:00+00:00"})


def test_get_queue_hides_superseded_active_item_when_race_is_inactive():
    """A race that already moved to draft under another run should not keep an old queue item active."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_queue_doc = _make_existing_doc(
        {
            "id": "item-stale",
            "race_id": "ga-senate-2026",
            "run_id": "run-stale",
            "status": "running",
            "created_at": "2026-05-15T00:18:00+00:00",
        }
    )
    stale_ref = MagicMock()

    active_run_doc = _make_existing_doc(
        {
            "run_id": "run-stale",
            "race_id": "ga-senate-2026",
            "status": "running",
        }
    )
    run_ref = MagicMock()
    run_ref.get.return_value = active_run_doc

    race_doc = _make_existing_doc(
        {
            "race_id": "ga-senate-2026",
            "status": "draft",
            "current_run_id": "run-completed",
        }
    )
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc

    queue_coll = MagicMock()
    queue_coll.order_by.return_value = queue_coll
    queue_coll.stream.return_value = iter([stale_queue_doc])
    queue_coll.document.return_value = stale_ref

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    def _coll(name):
        if name == "pipeline_queue":
            return queue_coll
        if name == "pipeline_runs":
            return runs_coll
        return races_coll

    db = _build_empty_firestore_mock()
    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/queue?active_only=true")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["running"] is False
    stale_ref.update.assert_called_once_with(
        {"status": "cancelled", "error": "Superseded by race current_run_id run-completed"}
    )


def test_get_queue_keeps_active_item_when_race_current_run_is_stale_terminal():
    """A stale terminal current_run_id should be cleared without cancelling a newer active queue item."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    queue_doc = _make_existing_doc(
        {
            "id": "item-new",
            "race_id": "ga-senate-2026",
            "run_id": "run-new",
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    queue_ref = MagicMock()

    def _run_document(run_id):
        ref = MagicMock()
        status = "cancelled" if run_id == "run-old" else "running"
        ref.get.return_value = _make_existing_doc({"run_id": run_id, "status": status})
        return ref

    race_ref = MagicMock()
    race_ref.get.return_value = _make_existing_doc(
        {"race_id": "ga-senate-2026", "status": "cancelled", "current_run_id": "run-old"}
    )

    queue_coll = MagicMock()
    queue_coll.order_by.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])
    queue_coll.document.return_value = queue_ref

    runs_coll = MagicMock()
    runs_coll.document.side_effect = _run_document

    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_queue":
            return queue_coll
        if name == "pipeline_runs":
            return runs_coll
        return races_coll

    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update_race,
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/queue?active_only=true")

    assert resp.status_code == 200
    body = resp.json()
    assert [item["run_id"] for item in body["items"]] == ["run-new"]
    queue_ref.update.assert_not_called()
    mock_update_race.assert_called_once_with("ga-senate-2026", {"current_run_id": None})


def test_active_runs_hides_stale_run_and_marks_queue_failed():
    """Global active run listing should self-heal old crashed runs."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    stale_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    run_doc = _make_existing_doc(
        {
            "run_id": "run-stale",
            "race_id": "ga-senate-2026",
            "status": "running",
            "started_at": stale_at,
            "progress_updated_at": stale_at,
        }
    )
    run_ref = MagicMock()
    runs_coll = MagicMock()
    runs_coll.where.return_value = runs_coll
    runs_coll.stream.return_value = iter([run_doc])
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-stale", "status": "running"}
    queue_doc.reference = MagicMock()
    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    races_coll = MagicMock()
    races_coll.document.return_value = _make_missing_doc_ref()

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        if name == "races":
            return races_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/runs/active")

    assert resp.status_code == 200
    assert resp.json() == {"runs": [], "count": 0}
    run_update = run_ref.update.call_args.args[0]
    assert run_update["status"] == "failed"
    assert "Marked stale by active run listing" in run_update["error"]
    queue_doc.reference.update.assert_called_once()
    assert queue_doc.reference.update.call_args.args[0]["status"] == "failed"


def test_active_runs_hides_superseded_inactive_race_run():
    """Old active runs should not appear after the race has published under another run."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    run_doc = _make_existing_doc(
        {
            "run_id": "run-stale",
            "race_id": "ga-senate-2026",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    run_ref = MagicMock()
    runs_coll = MagicMock()
    runs_coll.where.return_value = runs_coll
    runs_coll.stream.return_value = iter([run_doc])
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-stale", "status": "running"}
    queue_doc.reference = MagicMock()
    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    race_ref = MagicMock()
    race_ref.get.return_value = _make_existing_doc(
        {"race_id": "ga-senate-2026", "status": "published", "current_run_id": "run-completed"}
    )
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        if name == "races":
            return races_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/runs/active")

    assert resp.status_code == 200
    assert resp.json() == {"runs": [], "count": 0}
    update = {"status": "cancelled", "error": "Superseded by race current_run_id run-completed"}
    run_ref.update.assert_called_once_with(update)
    queue_doc.reference.update.assert_called_once_with(update)


def test_active_runs_keeps_run_when_race_current_run_is_stale_terminal():
    """A stale terminal current_run_id should not cause /runs/active to cancel the live run."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    run_doc = _make_existing_doc(
        {
            "run_id": "run-new",
            "race_id": "ga-senate-2026",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    new_run_ref = MagicMock()
    old_run_ref = MagicMock()
    old_run_ref.get.return_value = _make_existing_doc({"run_id": "run-old", "status": "cancelled"})

    runs_coll = MagicMock()
    runs_coll.where.return_value = runs_coll
    runs_coll.stream.return_value = iter([run_doc])
    runs_coll.document.side_effect = lambda run_id: old_run_ref if run_id == "run-old" else new_run_ref

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([])

    race_ref = MagicMock()
    race_ref.get.return_value = _make_existing_doc(
        {"race_id": "ga-senate-2026", "status": "published", "current_run_id": "run-old"}
    )
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        if name == "races":
            return races_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update_race,
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/runs/active")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["runs"][0]["run_id"] == "run-new"
    new_run_ref.update.assert_not_called()
    mock_update_race.assert_called_once_with("ga-senate-2026", {"current_run_id": None})


def test_list_runs_merges_active_runs_missing_from_recent_query():
    """The dashboard run list should count active continuations even if recent ordering misses them."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    recent_doc = _make_existing_doc(
        {
            "run_id": "run-old",
            "race_id": "old-race-2026",
            "status": "completed",
            "started_at": "2026-04-01T00:00:00+00:00",
        }
    )
    active_doc = _make_existing_doc(
        {
            "run_id": "run-active",
            "race_id": "ga-senate-2026",
            "status": "running",
            "progress_updated_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    recent_query = MagicMock()
    recent_query.limit.return_value = recent_query
    recent_query.stream.return_value = iter([recent_doc])

    active_query = MagicMock()
    active_query.stream.return_value = iter([active_doc])

    runs_coll = MagicMock()
    runs_coll.order_by.return_value = recent_query
    runs_coll.where.return_value = active_query
    runs_coll.document.return_value = MagicMock()

    races_coll = MagicMock()
    races_coll.document.return_value = _make_missing_doc_ref()

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([])

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "races":
            return races_coll
        if name == "pipeline_queue":
            return queue_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/runs?limit=10")

    assert resp.status_code == 200
    body = resp.json()
    assert body["active_count"] == 1
    assert body["total_count"] == 2
    assert [run["run_id"] for run in body["runs"]] == ["run-active", "run-old"]


def test_list_runs_uses_completed_and_progress_timestamps_for_recent_updates():
    """Runs tab should surface recently completed/progressed runs even when started_at is old."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    old_started_doc = _make_existing_doc(
        {
            "run_id": "run-started-old",
            "race_id": "old-race-2026",
            "status": "completed",
            "started_at": "2026-04-01T00:00:00+00:00",
            "completed_at": "2026-04-01T00:30:00+00:00",
        }
    )
    recently_completed_doc = _make_existing_doc(
        {
            "run_id": "run-completed-new",
            "race_id": "ar-governor-2026",
            "status": "completed",
            "started_at": "2026-04-01T00:00:00+00:00",
            "completed_at": "2026-05-18T12:00:00+00:00",
        }
    )
    recently_progressed_doc = _make_existing_doc(
        {
            "run_id": "run-progress-new",
            "race_id": "ga-senate-2026",
            "status": "running",
            "started_at": "2026-04-01T00:00:00+00:00",
            "progress_updated_at": "2026-05-18T12:01:00+00:00",
        }
    )

    def _query_for_order(field, **_kwargs):
        query = MagicMock()
        query.limit.return_value = query
        if field == "started_at":
            query.stream.return_value = iter([old_started_doc])
        elif field == "completed_at":
            query.stream.return_value = iter([recently_completed_doc])
        elif field == "progress_updated_at":
            query.stream.return_value = iter([recently_progressed_doc])
        else:
            query.stream.return_value = iter([])
        return query

    active_query = MagicMock()
    active_query.stream.return_value = iter([recently_progressed_doc])

    runs_coll = MagicMock()
    runs_coll.order_by.side_effect = _query_for_order
    runs_coll.where.return_value = active_query
    runs_coll.document.return_value = MagicMock()

    races_coll = MagicMock()
    races_coll.document.return_value = _make_missing_doc_ref()

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([])

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "races":
            return races_coll
        if name == "pipeline_queue":
            return queue_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/runs?limit=10")

    assert resp.status_code == 200
    body = resp.json()
    assert [run["run_id"] for run in body["runs"]] == [
        "run-progress-new",
        "run-completed-new",
        "run-started-old",
    ]


def test_queue_race_success():
    """POST /api/races/queue with SKIP_AUTH writes to Firestore and returns added list."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    db = _build_empty_firestore_mock()
    added_docs: dict[str, dict] = {}

    def _capture_set(data, **_kw):
        pass  # just accept the call

    queue_doc_ref = MagicMock()
    queue_doc_ref.set.side_effect = _capture_set

    coll_queue = MagicMock()
    coll_queue.document.return_value = queue_doc_ref
    coll_queue.stream.return_value = iter([])
    coll_queue.order_by.return_value = coll_queue

    races_doc_ref = MagicMock()
    races_doc_ref.set.side_effect = lambda *a, **kw: None

    coll_races = MagicMock()
    coll_races.document.return_value = races_doc_ref

    def _coll(name):
        if name == "pipeline_queue":
            return coll_queue
        return coll_races

    db.collection.side_effect = _coll

    import importlib
    import sys

    # Reimport in a clean environment
    if "main" in sys.modules:
        import main as app_module

        firestore_helpers._fs_db = None  # reset singleton
    else:
        import main as app_module

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post(
            "/api/races/queue",
            json={"race_ids": ["az-01-senate-2026"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["added"]) == 1
    assert body["added"][0]["race_id"] == "az-01-senate-2026"
    assert body["errors"] == []


def test_queue_multiple_races_creates_independent_queue_items():
    """Batch queueing should create one queue document and run_id per race."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    db = _build_empty_firestore_mock()
    queue_docs: dict[str, dict] = {}
    race_updates: dict[str, dict] = {}

    def _queue_document(doc_id):
        ref = MagicMock()
        ref.set.side_effect = lambda data, **_kw: queue_docs.__setitem__(doc_id, data)
        return ref

    coll_queue = MagicMock()
    coll_queue.document.side_effect = _queue_document
    coll_queue.stream.return_value = iter([])
    coll_queue.order_by.return_value = coll_queue

    def _race_document(race_id):
        ref = MagicMock()
        ref.set.side_effect = lambda data, **_kw: race_updates.__setitem__(race_id, data)
        return ref

    coll_races = MagicMock()
    coll_races.document.side_effect = _race_document

    def _coll(name):
        if name == "pipeline_queue":
            return coll_queue
        if name == "races":
            return coll_races
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post(
            "/api/races/queue",
            json={"race_ids": ["az-senate-2026", "ga-governor-2026"], "options": {"cheap_mode": True}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert [item["race_id"] for item in body["added"]] == ["az-senate-2026", "ga-governor-2026"]
    assert len(queue_docs) == 2
    assert len({doc["run_id"] for doc in queue_docs.values()}) == 2
    assert {doc["race_id"] for doc in queue_docs.values()} == {"az-senate-2026", "ga-governor-2026"}
    assert race_updates["az-senate-2026"]["current_run_id"] != race_updates["ga-governor-2026"]["current_run_id"]


def test_queue_rejects_duplicate_race_ids_in_same_batch():
    """A batch should not create two active queue docs for the same race."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=_build_empty_firestore_mock()),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post(
            "/api/races/queue",
            json={"race_ids": ["az-senate-2026", "az-senate-2026"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["added"]) == 1
    assert body["errors"] == [{"race_id": "az-senate-2026", "error": "Duplicate race_id in request"}]


def test_queue_rejects_already_running_race():
    """Do not queue a race already marked queued/running."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    running_doc = _make_existing_doc({"race_id": "az-senate-2026", "status": "running"})
    running_ref = MagicMock()
    running_ref.get.return_value = running_doc

    coll_races = MagicMock()
    coll_races.document.return_value = running_ref

    coll_queue = MagicMock()
    coll_queue.stream.return_value = iter([])
    coll_queue.order_by.return_value = coll_queue

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return coll_races
        if name == "pipeline_queue":
            return coll_queue
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/queue", json={"race_ids": ["az-senate-2026"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == []
    assert body["errors"] == [{"race_id": "az-senate-2026", "error": "Race is already running"}]


def test_queue_allows_requeue_when_running_status_is_stale_terminal_run():
    """Queue endpoint should self-heal stale running metadata and allow requeue."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    running_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "status": "running",
            "current_run_id": "run-old",
            "draft_updated_at": "2026-05-18T00:59:45.686753+00:00",
        }
    )
    running_ref = MagicMock()
    running_ref.get.return_value = running_doc

    run_doc = _make_existing_doc({"run_id": "run-old", "status": "cancelled"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    queue_lookup_coll = MagicMock()
    queue_lookup_coll.where.return_value = queue_lookup_coll
    queue_lookup_coll.stream.return_value = iter([])

    queue_doc_ref = MagicMock()
    queue_create_coll = MagicMock()
    queue_create_coll.document.return_value = queue_doc_ref

    coll_races = MagicMock()
    coll_races.document.return_value = running_ref

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return coll_races
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            # queue endpoint uses .where(...).stream() and then .document(...).set(...)
            queue_lookup_coll.document.return_value = queue_doc_ref
            return queue_lookup_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update,
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/queue", json={"race_ids": ["az-senate-2026"]})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["added"]) == 1
    assert body["errors"] == []
    updates = [c.args for c in mock_update.call_args_list]
    assert any(args[0] == "az-senate-2026" and args[1].get("status") == "draft" for args in updates)
    assert any(args[0] == "az-senate-2026" and args[1].get("status") == "queued" for args in updates)


def test_single_race_run_rejects_already_running_race():
    """The single-race run endpoint should enforce the same active-race guard as batch queueing."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    running_doc = _make_existing_doc({"race_id": "az-senate-2026", "status": "running"})
    running_ref = MagicMock()
    running_ref.get.return_value = running_doc

    coll_races = MagicMock()
    coll_races.document.return_value = running_ref

    queue_doc_ref = MagicMock()
    coll_queue = MagicMock()
    coll_queue.document.return_value = queue_doc_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return coll_races
        if name == "pipeline_queue":
            return coll_queue
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/az-senate-2026/run", json={"cheap_mode": True})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Race is already running"
    queue_doc_ref.set.assert_not_called()


def test_single_race_run_allows_when_running_status_is_stale_terminal_run():
    """Single-race run endpoint should self-heal stale running metadata and proceed."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    running_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "status": "running",
            "current_run_id": "run-old",
            "draft_updated_at": "2026-05-18T00:59:45.686753+00:00",
        }
    )
    running_ref = MagicMock()
    running_ref.get.return_value = running_doc

    run_doc = _make_existing_doc({"run_id": "run-old", "status": "cancelled"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    queue_lookup_coll = MagicMock()
    queue_lookup_coll.where.return_value = queue_lookup_coll
    queue_lookup_coll.stream.return_value = iter([])

    queue_doc_ref = MagicMock()
    queue_create_coll = MagicMock()
    queue_create_coll.document.return_value = queue_doc_ref

    coll_races = MagicMock()
    coll_races.document.return_value = running_ref

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return coll_races
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            queue_lookup_coll.document.return_value = queue_doc_ref
            return queue_lookup_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update,
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/az-senate-2026/run", json={"cheap_mode": True})

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    updates = [c.args for c in mock_update.call_args_list]
    assert any(args[0] == "az-senate-2026" and args[1].get("status") == "draft" for args in updates)
    assert any(args[0] == "az-senate-2026" and args[1].get("status") == "queued" for args in updates)


def test_run_options_accept_cloud_function_review_fields():
    """Production races-api RunOptions should accept all UI/agent option fields."""
    from request_models import RunOptions

    opts = RunOptions(
        cheap_mode=False,
        save_artifact=True,
        enabled_steps=["review", "iteration"],
        research_model="gpt-test",
        claude_model="claude-test",
        gemini_model="gemini-test",
        grok_model="grok-test",
        review_providers=[" claude ", "gemini", "claude"],
    )

    dumped = opts.model_dump(exclude_none=True)
    assert dumped["save_artifact"] is True
    assert dumped["gemini_model"] == "gemini-test"
    assert dumped["grok_model"] == "grok-test"
    assert dumped["review_providers"] == ["claude", "gemini"]


def test_run_options_normalize_and_validate_pipeline_controls():
    """Production RunOptions should enforce the same controls as the agent handler."""
    from pydantic import ValidationError
    from request_models import RunOptions

    opts = RunOptions(enabled_steps=[" discovery ", "issues", "issues"], candidate_names=[" Alice ", "", "Alice"])
    assert opts.enabled_steps == ["discovery", "issues"]
    assert opts.candidate_names == ["Alice"]

    with pytest.raises(ValidationError):
        RunOptions(enabled_steps=["not-a-step"])

    with pytest.raises(ValidationError):
        RunOptions(enabled_steps=["iteration"])


# ---------------------------------------------------------------------------
# /api/races/queue — invalid race_id rejected
# ---------------------------------------------------------------------------


def test_queue_race_invalid_id():
    """POST /api/races/queue with an invalid race_id returns error, not exception."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    db = _build_empty_firestore_mock()

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.post(
            "/api/races/queue",
            json={"race_ids": ["../../../etc/passwd"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == []
    assert len(body["errors"]) == 1
    assert "invalid" in body["errors"][0]["error"].lower()


def test_list_drafts_returns_summaries_not_ids():
    """The web dashboard expects /api/races/drafts to return Firestore catalog summaries."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    draft_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "title": "Arizona Senate 2026",
            "office": "U.S. Senate",
            "jurisdiction": "Arizona",
            "state": "AZ",
            "election_date": "2026-11-03",
            "updated_utc": "2026-05-01T00:00:00Z",
            "status": "draft",
            "draft_updated_at": "2026-05-01T00:00:00Z",
            "candidates": [
                {
                    "name": "Alice Example",
                    "party": "D",
                    "incumbent": False,
                    "image_url": "https://example.com/a.jpg",
                }
            ],
        }
    )

    coll_races = MagicMock()
    coll_races.limit.return_value = coll_races
    coll_races.stream.return_value = iter([draft_doc])
    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: coll_races if name == "races" else MagicMock()

    from fastapi.testclient import TestClient

    with (patch("firestore_helpers._get_fs", return_value=db),):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races/drafts")

    assert resp.status_code == 200
    body = resp.json()
    assert body["races"][0]["id"] == "az-senate-2026"
    assert body["races"][0]["title"] == "Arizona Senate 2026"
    assert body["races"][0]["candidates"][0]["name"] == "Alice Example"


def test_list_races_uses_firestore_catalog_state_for_draft_flags():
    """Race list should expose draft/published flags from the Firestore catalog."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_doc = _make_existing_doc(
        {
            "race_id": "ga-senate-2026",
            "status": "published",
            "published_at": "2026-04-01T00:00:00Z",
            "published_updated_utc": "2026-04-01T00:00:00Z",
            "published_candidate_count": 3,
            "published_quality_grade": "B",
        }
    )
    active_draft_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "status": "published",
            "draft_updated_at": "2026-05-01T00:00:00Z",
            "draft_updated_utc": "2026-05-01T00:00:00Z",
            "draft_candidate_count": 4,
            "draft_quality_grade": "A",
            "published_at": "2026-04-01T00:00:00Z",
            "published_updated_utc": "2026-04-01T00:00:00Z",
            "published_candidate_count": 3,
            "published_quality_grade": "B",
        }
    )
    coll_races = MagicMock()
    coll_races.limit.return_value = coll_races
    coll_races.stream.return_value = iter([stale_doc, active_draft_doc])
    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: coll_races if name == "races" else MagicMock()

    from fastapi.testclient import TestClient

    with (patch("firestore_helpers._get_fs", return_value=db),):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races")

    assert resp.status_code == 200
    by_id = {race["race_id"]: race for race in resp.json()["races"]}
    assert by_id["ga-senate-2026"]["status"] == "published"
    assert by_id["ga-senate-2026"]["draft_exists"] is False
    assert by_id["ga-senate-2026"]["published_exists"] is True
    assert by_id["az-senate-2026"]["status"] == "published"
    assert by_id["az-senate-2026"]["draft_exists"] is True
    assert by_id["az-senate-2026"]["published_exists"] is True


def test_list_races_normalizes_empty_status_when_catalog_shows_draft():
    """Race list should surface draft status when draft metadata exists even if Firestore status is stale."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_doc = _make_existing_doc(
        {
            "race_id": "ri-senate-2026",
            "status": "empty",
            "draft_updated_at": "2026-06-13T23:14:48.340000+00:00",
            "draft_updated_utc": "2026-06-13T23:14:48.340000+00:00",
            "draft_candidate_count": 2,
            "draft_quality_grade": "A",
            "published_at": None,
            "published_updated_utc": None,
        }
    )
    coll_races = MagicMock()
    coll_races.limit.return_value = coll_races
    coll_races.stream.return_value = iter([stale_doc])
    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: coll_races if name == "races" else MagicMock()

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races")

    assert resp.status_code == 200
    race = resp.json()["races"][0]
    assert race["race_id"] == "ri-senate-2026"
    assert race["status"] == "draft"
    assert race["draft_exists"] is True
    assert race["published_exists"] is False


def test_list_races_exposes_public_and_draft_quality_separately():
    """Admin/MCP records should keep draft and published catalog metadata separate."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "ar-governor-2026",
            "status": "published",
            "draft_updated_at": "2026-05-18T02:22:28Z",
            "draft_updated_utc": "2026-05-18T02:22:28Z",
            "draft_candidate_count": 4,
            "draft_quality_grade": "A",
            "published_at": "2026-04-06T16:44:20Z",
            "published_updated_utc": "2026-04-06T16:44:20Z",
            "published_candidate_count": 3,
            "published_quality_grade": None,
        }
    )
    coll_races = MagicMock()
    coll_races.limit.return_value = coll_races
    coll_races.stream.return_value = iter([race_doc])
    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: coll_races if name == "races" else MagicMock()

    from fastapi.testclient import TestClient

    with (patch("firestore_helpers._get_fs", return_value=db),):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races")

    assert resp.status_code == 200
    race = resp.json()["races"][0]
    assert race["quality_grade"] is None
    assert race["published_quality_grade"] is None
    assert race["draft_quality_grade"] == "A"
    assert race["candidate_count"] == 3
    assert race["published_candidate_count"] == 3
    assert race["draft_candidate_count"] == 4
    assert race["has_unpublished_changes"] is True


def test_list_races_derives_run_counts_from_pipeline_runs():
    """The races table run count should reflect canonical pipeline_runs docs, not stale race metadata."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "nh-senate-2026",
            "status": "published",
            "total_runs": 0,
            "last_run_status": None,
        }
    )
    races_coll = MagicMock()
    races_coll.limit.return_value = races_coll
    races_coll.stream.return_value = iter([race_doc])

    run_docs = [
        _make_existing_doc(
            {
                "run_id": "run-old",
                "race_id": "nh-senate-2026",
                "status": "failed",
                "completed_at": "2026-05-17T01:00:00+00:00",
            }
        ),
        _make_existing_doc(
            {
                "run_id": "run-new",
                "race_id": "nh-senate-2026",
                "status": "completed",
                "completed_at": "2026-05-17T02:00:00+00:00",
            }
        ),
    ]
    runs_coll = MagicMock()
    runs_coll.stream.return_value = iter(run_docs)

    db = _build_empty_firestore_mock()

    def _collection(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        return MagicMock()

    db.collection.side_effect = _collection

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_list_race_ids", side_effect=lambda prefix: ["nh-senate-2026"] if prefix == "races" else []),
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races")

    assert resp.status_code == 200
    race = resp.json()["races"][0]
    assert race["total_runs"] == 2
    assert race["last_run_id"] == "run-new"
    assert race["last_run_status"] == "completed"


def test_list_races_auto_reconciles_stale_running_metadata():
    """List endpoint should self-heal stale running metadata so admin UI stays accurate."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "ar-senate-2026",
            "status": "running",
            "current_run_id": "run-old",
            "draft_updated_at": "2026-05-18T00:59:45.686753+00:00",
        }
    )
    race_ref = MagicMock()
    race_ref.get.side_effect = [
        race_doc,
        _make_existing_doc({"race_id": "ar-senate-2026", "status": "draft", "current_run_id": None}),
    ]

    races_coll = MagicMock()
    races_coll.limit.return_value = races_coll
    races_coll.stream.return_value = iter([race_doc])
    races_coll.document.return_value = race_ref

    run_doc = _make_existing_doc({"run_id": "run-old", "status": "cancelled"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref
    runs_coll.stream.return_value = iter([])

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([])

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        return MagicMock()

    db.collection.side_effect = _coll

    def _gcs_get(race_id, prefix):
        if race_id == "ar-senate-2026" and prefix == "drafts":
            return {"id": race_id}
        return None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", side_effect=_gcs_get),
        patch("gcs_helpers._gcs_list_race_ids", side_effect=lambda prefix: ["ar-senate-2026"] if prefix == "drafts" else []),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races?reconcile_active=true")

    assert resp.status_code == 200
    race = resp.json()["races"][0]
    assert race["status"] == "draft"
    assert race["current_run_id"] is None
    assert mock_update.called


def test_get_race_record_auto_reconciles_by_default():
    """Single race fetch should reconcile stale running metadata by default."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "ar-senate-2026",
            "status": "running",
            "current_run_id": "run-old",
            "draft_updated_at": "2026-05-18T00:59:45.686753+00:00",
        }
    )
    race_ref = MagicMock()
    race_ref.get.side_effect = [
        race_doc,
        _make_existing_doc({"race_id": "ar-senate-2026", "status": "draft", "current_run_id": None}),
    ]

    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    run_doc = _make_existing_doc({"run_id": "run-old", "status": "cancelled"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([])

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        return MagicMock()

    db.collection.side_effect = _coll

    def _gcs_get(race_id, prefix):
        if race_id == "ar-senate-2026" and prefix == "drafts":
            return {"id": race_id}
        return None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", side_effect=_gcs_get),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races/ar-senate-2026")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "draft"
    assert body["current_run_id"] is None
    assert mock_update.called


def test_recheck_marks_stale_running_race_failed():
    """A dead Cloud Function should not leave a race permanently running."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    race_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "status": "running",
            "current_run_id": "run-stale",
        }
    )
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    run_doc = _make_existing_doc(
        {
            "run_id": "run-stale",
            "race_id": "az-senate-2026",
            "status": "running",
            "progress_updated_at": stale_at,
        }
    )
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-stale", "status": "running", "started_at": stale_at}
    queue_doc.reference = MagicMock()
    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        return MagicMock()

    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", return_value=None),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/az-senate-2026/recheck")

    assert resp.status_code == 200
    run_update = run_ref.update.call_args.args[0]
    assert run_update["status"] == "failed"
    queue_update = queue_doc.reference.update.call_args.args[0]
    assert queue_update["status"] == "failed"
    race_update = mock_update.call_args.args[1]
    assert race_update["status"] == "failed"
    assert race_update["current_run_id"] is None


def test_recheck_clears_stale_current_run_on_inactive_race():
    """Recheck should clean inactive race records whose current_run_id points to a terminal run."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "status": "published",
            "current_run_id": "run-old",
        }
    )
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    run_ref = MagicMock()
    run_ref.get.return_value = _make_existing_doc({"run_id": "run-old", "status": "cancelled"})
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        return MagicMock()

    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/az-senate-2026/recheck")

    assert resp.status_code == 200
    mock_update.assert_called_once_with("az-senate-2026", {"current_run_id": None})


def test_recheck_all_marks_stale_running_races_failed():
    """Bulk recheck should reconcile every race record, not just one race."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    race_docs = [
        _make_existing_doc({"race_id": "az-senate-2026", "status": "running", "current_run_id": "run-az"}),
        _make_existing_doc({"race_id": "ga-governor-2026", "status": "draft"}),
    ]

    race_refs: dict[str, MagicMock] = {}

    def _race_document(race_id):
        if race_id not in race_refs:
            ref = MagicMock()
            doc_data = next((d.to_dict() for d in race_docs if d.to_dict().get("race_id") == race_id), {})
            ref.get.return_value = _make_existing_doc(doc_data)
            race_refs[race_id] = ref
        return race_refs[race_id]

    races_coll = MagicMock()
    races_coll.limit.return_value = races_coll
    races_coll.stream.return_value = iter(race_docs)
    races_coll.document.side_effect = _race_document

    run_doc = _make_existing_doc(
        {
            "run_id": "run-az",
            "race_id": "az-senate-2026",
            "status": "running",
            "progress_updated_at": stale_at,
        }
    )
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-az", "status": "running", "started_at": stale_at}
    queue_doc.reference = MagicMock()
    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        return MagicMock()

    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", return_value=None),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/recheck")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 2
    assert body["updated"] == 1
    run_ref.update.assert_called()
    queue_doc.reference.update.assert_called()
    assert mock_update.call_args.args[0] == "az-senate-2026"
    assert mock_update.call_args.args[1]["status"] == "failed"


def test_recheck_clears_stale_current_run_for_cancelled_race():
    """Recheck should clear stale run pointers on inactive/cancelled race records."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "co-senate-2026",
            "status": "cancelled",
            "current_run_id": "run-cancelled-old",
        }
    )
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    run_doc = _make_existing_doc(
        {
            "run_id": "run-cancelled-old",
            "race_id": "co-senate-2026",
            "status": "cancelled",
        }
    )
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        return MagicMock()

    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/co-senate-2026/recheck")

    assert resp.status_code == 200
    mock_update.assert_called_once_with("co-senate-2026", {"current_run_id": None})


def test_recheck_all_clears_stale_current_run_for_inactive_race():
    """Bulk recheck should clear stale pointers even when race status is already inactive."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_docs = [
        _make_existing_doc({"race_id": "co-senate-2026", "status": "cancelled", "current_run_id": "run-old"}),
        _make_existing_doc({"race_id": "ar-governor-2026", "status": "draft"}),
    ]

    race_refs: dict[str, MagicMock] = {}

    def _race_document(race_id):
        if race_id not in race_refs:
            ref = MagicMock()
            doc_data = next((d.to_dict() for d in race_docs if d.to_dict().get("race_id") == race_id), {})
            ref.get.return_value = _make_existing_doc(doc_data)
            race_refs[race_id] = ref
        return race_refs[race_id]

    races_coll = MagicMock()
    races_coll.limit.return_value = races_coll
    races_coll.stream.return_value = iter(race_docs)
    races_coll.document.side_effect = _race_document

    run_doc = _make_existing_doc(
        {
            "run_id": "run-old",
            "race_id": "co-senate-2026",
            "status": "failed",
        }
    )
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc
    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "races":
            return races_coll
        if name == "pipeline_runs":
            return runs_coll
        return MagicMock()

    db.collection.side_effect = _coll

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/recheck")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 2
    assert body["updated"] == 1
    mock_update.assert_called_once_with("co-senate-2026", {"current_run_id": None})


def test_recheck_reconciles_empty_race_to_draft_when_draft_exists():
    """Recheck should correct inactive status drift from empty to draft based on storage."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_doc = _make_existing_doc(
        {
            "race_id": "ar-senate-2026",
            "status": "empty",
            "current_run_id": None,
            "draft_updated_at": "2026-05-18T00:59:45.686753+00:00",
        }
    )
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: races_coll if name == "races" else MagicMock()

    def _gcs_get(race_id, prefix):
        if race_id != "ar-senate-2026":
            return None
        if prefix == "drafts":
            return {"id": race_id}
        return None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", side_effect=_gcs_get),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/ar-senate-2026/recheck")

    assert resp.status_code == 200
    assert mock_update.call_args.args[0] == "ar-senate-2026"
    update = mock_update.call_args.args[1]
    assert update["status"] == "draft"
    assert update["current_run_id"] is None
    assert update["draft_updated_at"] == "2026-05-18T00:59:45.686753+00:00"
    assert update["published_at"] is None


def test_recheck_all_reconciles_empty_to_draft_from_storage():
    """Bulk recheck should also reconcile inactive storage drift for empty races."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_docs = [
        _make_existing_doc(
            {
                "race_id": "ar-senate-2026",
                "status": "empty",
                "current_run_id": None,
                "draft_updated_at": "2026-05-18T00:59:45.686753+00:00",
            }
        ),
        _make_existing_doc({"race_id": "co-senate-2026", "status": "draft", "current_run_id": None}),
    ]

    race_refs: dict[str, MagicMock] = {}

    def _race_document(race_id):
        if race_id not in race_refs:
            ref = MagicMock()
            doc_data = next((d.to_dict() for d in race_docs if d.to_dict().get("race_id") == race_id), {})
            ref.get.return_value = _make_existing_doc(doc_data)
            race_refs[race_id] = ref
        return race_refs[race_id]

    races_coll = MagicMock()
    races_coll.limit.return_value = races_coll
    races_coll.stream.return_value = iter(race_docs)
    races_coll.document.side_effect = _race_document

    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: races_coll if name == "races" else MagicMock()

    def _gcs_get(race_id, prefix):
        if race_id == "ar-senate-2026" and prefix == "drafts":
            return {"id": race_id}
        return None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", side_effect=_gcs_get),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/recheck")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 2
    assert body["updated"] == 1
    assert mock_update.call_args.args[0] == "ar-senate-2026"
    update = mock_update.call_args.args[1]
    assert update["status"] == "draft"
    assert update["current_run_id"] is None
    assert update["draft_updated_at"] == "2026-05-18T00:59:45.686753+00:00"
    assert update["published_at"] is None


def test_recheck_all_backfills_catalog_for_gcs_only_race():
    """Bulk recheck should create a Firestore catalog record for races that already exist only in GCS."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    races_coll = MagicMock()
    races_coll.limit.return_value = races_coll
    races_coll.stream.return_value = iter([])

    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: races_coll if name == "races" else MagicMock()

    def _gcs_get(race_id, prefix):
        if race_id != "az-senate-2026":
            return None
        if prefix == "races":
            return {
                "id": race_id,
                "title": "Arizona Senate 2026",
                "office": "U.S. Senate",
                "jurisdiction": "Arizona",
                "state": "AZ",
                "election_date": "2026-11-03",
                "updated_utc": "2026-05-01T00:00:00Z",
                "candidates": [{"name": "Alice Example"}],
            }
        return None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_list_race_ids", side_effect=lambda prefix: ["az-senate-2026"] if prefix == "races" else []),
        patch("gcs_helpers._gcs_get_race_json", side_effect=_gcs_get),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/recheck")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["updated"] == 1
    update = mock_update.call_args.args[1]
    assert mock_update.call_args.args[0] == "az-senate-2026"
    assert update["status"] == "published"
    assert update["title"] == "Arizona Senate 2026"
    assert update["published_updated_utc"] == "2026-05-01T00:00:00Z"
    assert update["draft_updated_at"] is None


def test_recheck_single_backfills_missing_firestore_record_from_storage():
    """Single-race recheck should create a missing Firestore catalog record from storage."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    race_ref = MagicMock()
    race_ref.get.return_value = MagicMock(exists=False)
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: races_coll if name == "races" else MagicMock()

    def _gcs_get(race_id, prefix):
        if race_id != "ga-senate-2026":
            return None
        if prefix == "drafts":
            return {
                "id": race_id,
                "title": "Georgia Senate 2026",
                "office": "U.S. Senate",
                "jurisdiction": "Georgia",
                "state": "GA",
                "election_date": "2026-11-03",
                "updated_utc": "2026-06-01T00:00:00Z",
                "candidates": [{"name": "Pat Example"}],
                "validation_grade": {"grade": "A", "passed": True},
            }
        return None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_get_race_json", side_effect=_gcs_get),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/ga-senate-2026/recheck")

    assert resp.status_code == 200
    race = resp.json()["race"]
    assert race["status"] == "draft"
    assert race["title"] == "Georgia Senate 2026"
    assert race["draft_quality_grade"] == "A"
    update = mock_update.call_args.args[1]
    assert update["draft_updated_utc"] == "2026-06-01T00:00:00Z"


def test_publish_race_clears_draft_timestamp():
    """Publishing should clear draft metadata so the UI no longer shows a stale publishable draft."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    draft_json = {"id": "az-senate-2026", "title": "Arizona Senate 2026", "candidates": [{"name": "Alice"}]}

    with (
        patch("firestore_helpers._get_fs", return_value=_build_empty_firestore_mock()),
        patch("gcs_helpers._gcs_get_race_json", return_value=draft_json),
        patch("gcs_helpers._publish_race_gcs"),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/az-senate-2026/publish")

    assert resp.status_code == 200
    update = mock_update.call_args.args[1]
    assert update["status"] == "published"
    assert update["draft_updated_at"] is None
    assert update["current_run_id"] is None


def test_publish_race_rejects_failed_validation_grade():
    """A draft that failed review should not be publishable."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    draft_json = {
        "id": "nh-senate-2026",
        "title": "New Hampshire Senate 2026",
        "candidates": [{"name": "Alice"}],
        "validation_grade": {"grade": "C", "score": 75, "passed": False},
    }

    with (
        patch("firestore_helpers._get_fs", return_value=_build_empty_firestore_mock()),
        patch("gcs_helpers._gcs_get_race_json", return_value=draft_json),
        patch("gcs_helpers._publish_race_gcs") as mock_publish,
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/nh-senate-2026/publish")

    assert resp.status_code == 409
    assert "failed validation" in resp.json()["detail"]
    mock_publish.assert_not_called()
    mock_update.assert_not_called()


def test_gcs_publish_helper_rejects_failed_validation_grade():
    """The lower-level publish helper should also reject failed-review data."""
    failed_race = {
        "id": "nh-senate-2026",
        "validation_grade": {"grade": "C", "score": 75, "passed": False},
    }

    with (
        patch("gcs_helpers._gcs_archive_race") as mock_archive,
        patch("gcs_helpers._gcs_put_race_json") as mock_put,
        patch("gcs_helpers._gcs_delete_race_json") as mock_delete,
        pytest.raises(ValueError, match="failed validation"),
    ):
        gcs_helpers.publish_race_to_gcs("nh-senate-2026", failed_race)

    mock_archive.assert_not_called()
    mock_put.assert_not_called()
    mock_delete.assert_not_called()


def test_gcs_publish_helper_rejects_incomplete_pipeline_state():
    incomplete_race = {
        "id": "nh-senate-2026",
        "pipeline_state": {
            "complete": False,
            "remaining_candidates": ["Alice"],
            "remaining_steps": ["issues", "review"],
        },
    }

    with pytest.raises(ValueError, match="operationally incomplete"):
        gcs_helpers.publish_race_to_gcs("nh-senate-2026", incomplete_race)


def test_summary_index_retries_concurrent_write():
    from google.api_core.exceptions import PreconditionFailed

    first_blob = MagicMock()
    first_blob.generation = 7
    first_blob.download_as_text.return_value = "[]"
    first_blob.upload_from_string.side_effect = PreconditionFailed("changed")

    second_blob = MagicMock()
    second_blob.generation = 8
    second_blob.download_as_text.return_value = "[]"

    bucket = MagicMock()
    bucket.blob.side_effect = [first_blob, second_blob]
    client = MagicMock()
    client.bucket.return_value = bucket

    with (
        patch.object(gcs_helpers, "_GCS_BUCKET", "test-bucket"),
        patch("gcs_helpers._get_gcs_admin", return_value=client),
    ):
        gcs_helpers.update_gcs_summaries_json({"az-senate-2026": {"id": "az-senate-2026", "candidates": []}})

    first_blob.upload_from_string.assert_called_once()
    second_blob.upload_from_string.assert_called_once()
    assert second_blob.upload_from_string.call_args.kwargs["if_generation_match"] == 8


def test_gcs_race_id_listing_ignores_summaries_index():
    race_blob = MagicMock()
    race_blob.name = "races/az-senate-2026.json"
    index_blob = MagicMock()
    index_blob.name = "races/summaries.json"
    bucket = MagicMock()
    bucket.list_blobs.return_value = [race_blob, index_blob]
    client = MagicMock()
    client.bucket.return_value = bucket

    with (
        patch.object(gcs_helpers, "_GCS_BUCKET", "test-bucket"),
        patch("gcs_helpers._get_gcs_admin", return_value=client),
    ):
        assert gcs_helpers._gcs_list_race_ids("races") == ["az-senate-2026"]


def test_summary_index_raises_when_gcs_client_is_unavailable():
    with (
        patch.object(gcs_helpers, "_GCS_BUCKET", "test-bucket"),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        pytest.raises(RuntimeError, match="GCS client is unavailable"),
    ):
        gcs_helpers.update_gcs_summaries_json({"az-senate-2026": None})


def test_batch_publish_skips_failed_validation_grade():
    """Batch publish should publish good drafts and report failed-review drafts as errors."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    def fake_get(race_id, prefix):
        if race_id == "az-senate-2026":
            return {"id": race_id, "candidates": [{"name": "Alice"}], "validation_grade": {"passed": True}}
        return {
            "id": race_id,
            "candidates": [{"name": "Bob"}],
            "validation_grade": {"grade": "C", "score": 75, "passed": False},
        }

    with (
        patch("firestore_helpers._get_fs", return_value=_build_empty_firestore_mock()),
        patch("gcs_helpers._gcs_get_race_json", side_effect=fake_get),
        patch("gcs_helpers._publish_race_gcs") as mock_publish,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/publish", json={"race_ids": ["az-senate-2026", "nh-senate-2026"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["published"] == ["az-senate-2026"]
    assert body["errors"][0]["race_id"] == "nh-senate-2026"
    assert "failed validation" in body["errors"][0]["error"]
    mock_publish.assert_called_once()


def test_unpublish_without_draft_does_not_create_phantom_draft():
    """Unpublish should not mark a race draft unless a draft blob actually exists."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=_build_empty_firestore_mock()),
        patch("gcs_helpers._gcs_get_race_json", return_value=None),
        patch("gcs_helpers._gcs_delete_race_json", return_value=True),
        patch("firestore_helpers._fs_update_race") as mock_update,
    ):
        tc = TestClient(app_module.app)
        resp = tc.post("/api/races/ga-senate-2026/unpublish")

    assert resp.status_code == 200
    update = mock_update.call_args.args[1]
    assert update["status"] == "empty"
    assert update["published_at"] is None
    assert update["draft_updated_at"] is None


def test_admin_chat_reply_parser_extracts_action():
    """Production admin chat should return the action shape consumed by the frontend."""
    from routers.pipeline import _parse_admin_chat_reply

    parsed = _parse_admin_chat_reply(
        'Queue this race.\nACTION:{"type":"queue_run","race_ids":["az-senate-2026"],"options":{},"description":"Refresh Arizona"}'
    )

    assert parsed["reply"] == "Queue this race."
    assert parsed["action"]["type"] == "queue_run"
    assert parsed["action"]["options"]["cheap_mode"] is True
    assert parsed["question"] is None
    assert parsed["thinking_steps"]


def test_admin_chat_action_race_records_from_context():
    """Admin chat responses should include record details for proposed race actions."""
    from routers.pipeline import _race_records_for_action

    action = {"type": "queue_run", "race_ids": ["az-senate-2026"]}
    context = [
        {"race_id": "az-senate-2026", "title": "Arizona Senate 2026", "status": "draft"},
        {"race_id": "ga-governor-2026", "title": "Georgia Governor 2026", "status": "published"},
    ]

    records = _race_records_for_action(action, context)

    assert records == [{"race_id": "az-senate-2026", "title": "Arizona Senate 2026", "status": "draft"}]


def test_admin_chat_reply_parser_extracts_question():
    """Production admin chat should support clarification questions."""
    from routers.pipeline import _parse_admin_chat_reply

    parsed = _parse_admin_chat_reply('Need detail.\nQUESTION:{"text":"Which race?"}')

    assert parsed["reply"] == "Need detail."
    assert parsed["question"] == "Which race?"
    assert parsed["action"] is None


# ---------------------------------------------------------------------------
# /runs/{run_id}/logs — returns sliced entries
# ---------------------------------------------------------------------------


def test_get_run_logs_since():
    """GET /runs/{run_id}/logs?since=2 returns only entries from index 2 onward."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    entries = [{"timestamp": f"2026-01-01T00:00:0{i}Z", "level": "info", "message": f"msg {i}"} for i in range(5)]

    def _make_log_doc(data):
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = dict(data)
        return doc

    log_docs = [_make_log_doc(e) for e in entries]

    db = _build_empty_firestore_mock()

    # Build nested subcollection mock: pipeline_runs → {run_id} → logs
    log_coll = MagicMock()
    log_coll.stream.return_value = iter(log_docs)

    run_doc_ref = MagicMock()
    run_doc_ref.collection.return_value = log_coll

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_doc_ref

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/runs/run-abc/logs?since=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["logs"]) == 3  # entries 2, 3, 4
    assert body["logs"][0]["message"] == "msg 2"


def test_delete_active_run_cancels_matching_queue_item():
    """Deleting an active run should cancel its Firestore queue item so the Cloud Function stops."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    run_doc = _make_existing_doc({"run_id": "run-active", "race_id": "az-senate-2026", "status": "running"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-active", "status": "running"}
    queue_doc.reference = MagicMock()

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    race_doc = _make_existing_doc({"race_id": "az-senate-2026", "status": "running", "current_run_id": "run-active"})
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        if name == "races":
            return races_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.delete("/runs/run-active")

    assert resp.status_code == 200
    assert resp.json()["message"] == "Run cancelled"
    run_ref.update.assert_called_with({"status": "cancelled"})
    queue_doc.reference.update.assert_called_with({"status": "cancelled"})
    race_ref.set.assert_called()


def test_delete_superseded_active_run_does_not_cancel_published_race():
    """Cancelling an old active run must not overwrite a completed race record."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    run_doc = _make_existing_doc({"run_id": "run-stale", "race_id": "ga-senate-2026", "status": "running"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-stale", "status": "running"}
    queue_doc.reference = MagicMock()

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    race_doc = _make_existing_doc({"race_id": "ga-senate-2026", "status": "published", "current_run_id": "run-completed"})
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        if name == "races":
            return races_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.delete("/runs/run-stale")

    assert resp.status_code == 200
    assert resp.json()["message"] == "Run cancelled"
    run_ref.update.assert_called_with({"status": "cancelled"})
    queue_doc.reference.update.assert_called_with({"status": "cancelled"})
    race_ref.set.assert_not_called()


def test_delete_race_scoped_active_run_cancels_matching_queue_item():
    """Race-scoped run deletion should cancel the same queue item as the global run endpoint."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    run_doc = _make_existing_doc({"run_id": "run-active", "race_id": "az-senate-2026", "status": "running"})
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    runs_coll = MagicMock()
    runs_coll.document.return_value = run_ref

    queue_doc = MagicMock()
    queue_doc.to_dict.return_value = {"run_id": "run-active", "status": "pending"}
    queue_doc.reference = MagicMock()

    queue_coll = MagicMock()
    queue_coll.where.return_value = queue_coll
    queue_coll.stream.return_value = iter([queue_doc])

    race_doc = _make_existing_doc({"race_id": "az-senate-2026", "status": "running"})
    race_ref = MagicMock()
    race_ref.get.return_value = race_doc
    races_coll = MagicMock()
    races_coll.document.return_value = race_ref

    db = _build_empty_firestore_mock()

    def _coll(name):
        if name == "pipeline_runs":
            return runs_coll
        if name == "pipeline_queue":
            return queue_coll
        if name == "races":
            return races_coll
        return MagicMock()

    db.collection.side_effect = _coll

    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._get_gcs_admin", return_value=None),
        patch("gcs_helpers._GCS_BUCKET", ""),
    ):
        tc = TestClient(app_module.app)
        resp = tc.delete("/api/races/az-senate-2026/runs/run-active")

    assert resp.status_code == 200
    assert resp.json()["message"] == "Run cancelled"
    run_ref.update.assert_called_with({"status": "cancelled"})
    queue_doc.reference.update.assert_called_with({"status": "cancelled"})
    race_ref.set.assert_called()


# ---------------------------------------------------------------------------
# verify_token — SKIP_AUTH bypasses JWT validation
# ---------------------------------------------------------------------------


def test_verify_token_skip_auth():
    """With SKIP_AUTH=true, verify_token returns {} without hitting Auth0."""
    os.environ["SKIP_AUTH"] = "true"

    import asyncio

    import auth

    # verify_token reads SKIP_AUTH at call time — no module reload required.
    result = asyncio.run(auth.verify_token(None))
    assert result == {}


# ---------------------------------------------------------------------------
# verify_token — missing credentials returns 401 when auth is enabled
# ---------------------------------------------------------------------------


def test_verify_token_missing_credentials():
    """With SKIP_AUTH=false, missing credentials raises 401."""
    os.environ["SKIP_AUTH"] = "false"
    os.environ["AUTH0_DOMAIN"] = "example.auth0.com"
    os.environ["AUTH0_AUDIENCE"] = "https://api.example.com"

    import asyncio

    import auth
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.verify_token(None))

    assert exc_info.value.status_code == 401


def test_verify_token_accepts_admin_api_key():
    """With ADMIN_API_KEY set, X-Admin-Key authorizes non-browser admin clients."""
    os.environ["SKIP_AUTH"] = "false"
    os.environ["ADMIN_API_KEY"] = "secret"
    os.environ.pop("AUTH0_DOMAIN", None)
    os.environ.pop("AUTH0_AUDIENCE", None)

    import asyncio

    import auth

    result = asyncio.run(auth.verify_token(None, x_admin_key="secret"))
    assert result == {"auth": "admin_api_key"}


def test_verify_token_rejects_wrong_admin_api_key_without_bearer():
    """Wrong X-Admin-Key returns 401 before Auth0 fallback when no bearer token is present."""
    os.environ["SKIP_AUTH"] = "false"
    os.environ["ADMIN_API_KEY"] = "secret"
    os.environ.pop("AUTH0_DOMAIN", None)
    os.environ.pop("AUTH0_AUDIENCE", None)

    import asyncio

    import auth
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.verify_token(None, x_admin_key="wrong"))

    assert exc_info.value.status_code == 401


def test_admin_endpoint_accepts_admin_api_key_header(monkeypatch):
    """Any verify_token-protected admin route should accept X-Admin-Key."""
    monkeypatch.setenv("SKIP_AUTH", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)

    import main as app_module
    from fastapi.testclient import TestClient

    tc = TestClient(app_module.app)
    resp = tc.get("/steps", headers={"X-Admin-Key": "secret"})

    assert resp.status_code == 200
    assert "steps" in resp.json()
