import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def _make_existing_doc(data):
    doc = MagicMock()
    doc.exists = True
    doc.id = data.get("run_id") or data.get("id") or "doc-id"
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    return doc


def _build_empty_firestore_mock():
    db = MagicMock()
    return db


def test_prune_runs_endpoint():
    """DELETE /runs should query terminal runs and delete them using a batch delete."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    # Mock terminal runs
    run_docs = [
        _make_existing_doc({"run_id": "run-1", "status": "completed"}),
        _make_existing_doc({"run_id": "run-2", "status": "failed"}),
        _make_existing_doc({"run_id": "run-3", "status": "cancelled"}),
        _make_existing_doc({"run_id": "run-4", "status": "continued"}),
    ]

    runs_coll = MagicMock()
    runs_coll.where.return_value = runs_coll
    runs_coll.stream.side_effect = lambda: iter(run_docs)

    db = _build_empty_firestore_mock()
    db.collection.return_value = runs_coll

    # Mock batch
    batch_mock = MagicMock()
    db.batch.return_value = batch_mock

    import firestore_helpers
    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)
        resp = tc.delete("/runs")

    assert resp.status_code == 200
    body = resp.json()
    assert "Pruned 4 finished runs" in body["message"]
    assert body["count"] == 4

    # Check that batch delete was called on each document reference
    assert batch_mock.delete.call_count == 4
    batch_mock.commit.assert_called_once()


def test_pipeline_metrics_summary_hours_filter():
    """GET /pipeline/metrics/summary with hours parameter should filter runs prior to aggregation."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    now = datetime.now(timezone.utc)
    # Mock records: one recent (1 hour ago), one old (48 hours ago)
    metric_docs = [
        _make_existing_doc(
            {
                "run_id": "run-recent",
                "race_id": "az-senate-2026",
                "status": "completed",
                "started_at": (now - timedelta(hours=1)).isoformat(),
                "cheap_mode": True,
                "estimated_usd": 0.05,
                "candidate_count": 2,
            }
        ),
        _make_existing_doc(
            {
                "run_id": "run-old",
                "race_id": "ga-senate-2026",
                "status": "completed",
                "started_at": (now - timedelta(hours=48)).isoformat(),
                "cheap_mode": True,
                "estimated_usd": 0.15,
                "candidate_count": 4,
            }
        ),
    ]

    metrics_coll = MagicMock()
    metrics_coll.stream.side_effect = lambda: iter(metric_docs)

    db = _build_empty_firestore_mock()
    db.collection.return_value = metrics_coll

    import firestore_helpers
    import main as app_module

    firestore_helpers._fs_db = None

    from fastapi.testclient import TestClient

    with patch("firestore_helpers._get_fs", return_value=db):
        tc = TestClient(app_module.app)

        # Test without hours filter
        resp_all = tc.get("/pipeline/metrics/summary")
        assert resp_all.status_code == 200
        body_all = resp_all.json()

        # Test with 24 hours filter
        resp_filtered = tc.get("/pipeline/metrics/summary?hours=24")
        assert resp_filtered.status_code == 200
        body_filtered = resp_filtered.json()

        assert body_filtered["total_runs"] == 1
        assert body_filtered["total_usd"] == 0.05
