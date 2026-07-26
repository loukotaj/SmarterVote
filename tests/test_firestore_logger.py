"""Tests for FirestoreLogger (pipeline_client/backend/firestore_logger.py)."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from pipeline_client.backend.firestore_logger import FirestoreLogger


@pytest.fixture
def mock_db():
    """Return a mock Firestore client."""
    with patch("pipeline_client.backend.firestore_logger._get_db") as mock_get_db:
        db = MagicMock()
        mock_get_db.return_value = db
        yield db


def test_log_writes_to_subcollection(mock_db):
    """log() batches entries and flush() writes them to pipeline_runs/{run_id}/logs/."""
    logger = FirestoreLogger("run-001")
    logger.log("info", "Test message", step="issues")
    logger.flush()

    run_ref = mock_db.collection.return_value.document.return_value
    logs_col = run_ref.collection.return_value
    doc_ref = logs_col.document.return_value
    batch = mock_db.batch.return_value
    batch.set.assert_called_once()
    batch.commit.assert_called_once()
    assert batch.set.call_args.args[0] == doc_ref
    written = batch.set.call_args.args[1]
    assert written["level"] == "info"
    assert written["message"] == "Test message"
    assert written["step"] == "issues"
    assert written["run_id"] == "run-001"


def test_log_flushes_at_configured_batch_size(mock_db, monkeypatch):
    monkeypatch.setenv("PIPELINE_FIRESTORE_LOG_BATCH_SIZE", "2")
    logger = FirestoreLogger("run-batch")

    logger.log("info", "one")
    assert mock_db.batch.return_value.commit.call_count == 0

    logger.log("info", "two")

    assert mock_db.batch.return_value.set.call_count == 2
    assert mock_db.batch.return_value.commit.call_count == 1


def test_log_truncates_before_batch_write(mock_db, monkeypatch):
    monkeypatch.setenv("PIPELINE_MAX_LOG_MESSAGE_CHARS", "256")
    logger = FirestoreLogger("run-truncate")

    logger.log("warning", "x" * 1000)
    logger.flush()

    written = mock_db.batch.return_value.set.call_args.args[1]
    assert len(written["message"]) <= 256
    assert written["truncated"] is True
    assert logger.truncated_log_count == 1


def test_log_swallows_exceptions():
    """log() silently handles Firestore errors."""
    with patch("pipeline_client.backend.firestore_logger._get_db", side_effect=RuntimeError("boom")):
        logger = FirestoreLogger("run-002")
        logger.log("error", "Should not raise")  # must not propagate


def test_update_progress_merges_run_doc(mock_db):
    """update_progress() merges fields into pipeline_runs/{run_id}."""
    logger = FirestoreLogger("run-003")
    logger.update_progress(
        42,
        current_step="issues",
        current_step_progress=17,
        progress_message="Issues checkpoint - Alice - Healthcare",
        status="running",
    )

    run_ref = mock_db.collection.return_value.document.return_value
    run_ref.set.assert_called_once()
    merged = run_ref.set.call_args[0][0]
    assert merged["progress"] == 42
    assert merged["current_step"] == "issues"
    assert merged["current_step_progress"] == 17
    assert merged["progress_message"] == "Issues checkpoint - Alice - Healthcare"
    assert merged["status"] == "running"


def test_mark_completed(mock_db):
    """mark_completed() sets status=completed and progress=100."""
    logger = FirestoreLogger("run-004")
    logger.mark_completed(duration_ms=5000)

    run_ref = mock_db.collection.return_value.document.return_value
    run_ref.set.assert_called_once()
    data = run_ref.set.call_args[0][0]
    assert data["status"] == "completed"
    assert data["progress"] == 100
    assert data["duration_ms"] == 5000


def test_mark_failed(mock_db):
    """mark_failed() sets status=failed with error message."""
    logger = FirestoreLogger("run-005")
    logger.mark_failed("Something went wrong")

    run_ref = mock_db.collection.return_value.document.return_value
    run_ref.set.assert_called_once()
    data = run_ref.set.call_args[0][0]
    assert data["status"] == "failed"
    assert "Something went wrong" in data["error"]


def test_mark_completed_omits_run_health_when_not_provided(mock_db):
    """Backward compat: existing callers that don't pass run_health get no such key."""
    logger = FirestoreLogger("run-006")
    logger.mark_completed(duration_ms=1000)

    data = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert "run_health" not in data


def test_mark_completed_persists_run_health_when_provided(mock_db):
    """run_health is the "did this actually succeed" verdict — independent of status,
    which stays "completed" here even when the verdict is degraded/failed."""
    logger = FirestoreLogger("run-007")
    run_health = {
        "status": "degraded",
        "reasons": ["step_no_data"],
        "step_failures": [{"step": "finance", "reason": "step_no_data", "detail": None}],
        "summary": "finance: step_no_data",
    }
    logger.mark_completed(duration_ms=1000, run_health=run_health)

    data = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert data["status"] == "completed"
    assert data["run_health"] == run_health


def test_mark_failed_persists_run_health_when_provided(mock_db):
    logger = FirestoreLogger("run-008")
    run_health = {"status": "failed", "reasons": ["cancelled"], "step_failures": [], "summary": None}
    logger.mark_failed("cancelled by admin", run_health=run_health)

    data = mock_db.collection.return_value.document.return_value.set.call_args[0][0]
    assert data["run_health"] == run_health


def test_mark_handoff_keeps_logical_run_active(mock_db):
    """mark_handoff() records an invocation transition without ending the run."""
    logger = FirestoreLogger("run-006")
    logger.mark_handoff("queue-007")

    run_ref = mock_db.collection.return_value.document.return_value
    run_ref.set.assert_called_once()
    data = run_ref.set.call_args[0][0]
    assert data["status"] == "running"
    assert data["continuation_item_id"] == "queue-007"
    assert data["continuation_count"] is not None


def test_get_db_falls_back_to_default_project_client():
    """_get_db() should use firestore.Client() when project env vars are absent."""
    client_mock = MagicMock()
    firestore_mod = types.ModuleType("google.cloud.firestore")
    setattr(firestore_mod, "Client", client_mock)
    cloud_mod = types.ModuleType("google.cloud")
    setattr(cloud_mod, "firestore", firestore_mod)
    google_mod = types.ModuleType("google")
    setattr(google_mod, "cloud", cloud_mod)

    with (
        patch("pipeline_client.backend.firestore_logger._db", None),
        patch("pipeline_client.backend.firestore_logger.os.getenv", return_value=None),
        patch.dict(
            sys.modules,
            {
                "google": google_mod,
                "google.cloud": cloud_mod,
                "google.cloud.firestore": firestore_mod,
            },
            clear=False,
        ),
    ):
        from pipeline_client.backend import firestore_logger as fl

        fl._get_db()

    client_mock.assert_called_once_with()


def test_get_db_uses_project_when_configured():
    """_get_db() should pass project when FIRESTORE_PROJECT/PROJECT_ID is set."""
    client_mock = MagicMock()
    firestore_mod = types.ModuleType("google.cloud.firestore")
    setattr(firestore_mod, "Client", client_mock)
    cloud_mod = types.ModuleType("google.cloud")
    setattr(cloud_mod, "firestore", firestore_mod)
    google_mod = types.ModuleType("google")
    setattr(google_mod, "cloud", cloud_mod)

    with (
        patch("pipeline_client.backend.firestore_logger._db", None),
        patch("pipeline_client.backend.firestore_logger.os.getenv", return_value="smartervote"),
        patch.dict(
            sys.modules,
            {
                "google": google_mod,
                "google.cloud": cloud_mod,
                "google.cloud.firestore": firestore_mod,
            },
            clear=False,
        ),
    ):
        from pipeline_client.backend import firestore_logger as fl

        fl._get_db()

    client_mock.assert_called_once_with(project="smartervote")
