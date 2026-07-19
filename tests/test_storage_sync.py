import json
import pathlib
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

from pipeline_client.backend.models import RunInfo, RunStatus
from pipeline_client.backend.race_manager import RaceManager

# Add races-api to path so we can test gcs_helpers directly.
_RACES_API_DIR = pathlib.Path(__file__).parent.parent / "services" / "races-api"
if str(_RACES_API_DIR) not in sys.path:
    sys.path.insert(0, str(_RACES_API_DIR))

import gcs_helpers  # noqa: E402


def test_gcs_get_race_json_returns_blob_when_bucket_configured(monkeypatch):
    """When GCS bucket is set and blob exists, _gcs_get_race_json returns the parsed JSON."""
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = json.dumps({"id": "races:ga-senate-2026:gcs"})

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    monkeypatch.setattr(gcs_helpers, "_GCS_BUCKET", "test-bucket")
    monkeypatch.setattr(gcs_helpers, "_get_gcs_admin", lambda: mock_client)

    data = gcs_helpers._gcs_get_race_json("ga-senate-2026", "races")

    assert data == {"id": "races:ga-senate-2026:gcs"}
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("races/ga-senate-2026.json")


def test_gcs_get_race_json_returns_none_when_no_bucket(monkeypatch):
    """When GCS bucket is not configured, _gcs_get_race_json returns None without calling GCS."""
    monkeypatch.setattr(gcs_helpers, "_GCS_BUCKET", "")
    # Ensure _get_gcs_admin is never called
    called = []
    monkeypatch.setattr(gcs_helpers, "_get_gcs_admin", lambda: called.append(1) or None)

    data = gcs_helpers._gcs_get_race_json("ga-senate-2026", "drafts")

    assert data is None
    assert called == [], "_get_gcs_admin should not be called when bucket is empty"


def test_gcs_put_race_json_preserves_storage_contract(monkeypatch):
    """The adapter must use the canonical object path and JSON content type."""
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    payload = {"id": "ga-senate-2026", "candidates": [{"name": "Example"}]}
    monkeypatch.setattr(gcs_helpers, "_GCS_BUCKET", "test-bucket")
    monkeypatch.setattr(gcs_helpers, "_get_gcs_admin", lambda: mock_client)

    assert gcs_helpers._gcs_put_race_json("ga-senate-2026", "drafts", payload) is True

    mock_bucket.blob.assert_called_once_with("drafts/ga-senate-2026.json")
    serialized = mock_blob.upload_from_string.call_args.args[0]
    assert json.loads(serialized) == payload
    assert mock_blob.upload_from_string.call_args.kwargs["content_type"] == "application/json"


def test_gcs_get_race_json_rejects_malformed_provider_payload(monkeypatch):
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = "not-json"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    monkeypatch.setattr(gcs_helpers, "_GCS_BUCKET", "test-bucket")
    monkeypatch.setattr(gcs_helpers, "_get_gcs_admin", lambda: mock_client)

    assert gcs_helpers._gcs_get_race_json("ga-senate-2026", "drafts") is None


def test_race_manager_get_run_prefers_firestore_over_local_cache():
    manager = RaceManager()

    stale_local = RunInfo(
        run_id="run-1",
        status=RunStatus.RUNNING,
        payload={"race_id": "ga-senate-2026"},
        options={},
        started_at=datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc),
        steps=[],
    )
    fresh_remote = RunInfo(
        run_id="run-1",
        status=RunStatus.CANCELLED,
        payload={"race_id": "ga-senate-2026"},
        options={},
        started_at=datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 26, 0, 5, tzinfo=timezone.utc),
        steps=[],
    )
    manager._local_runs = {"ga-senate-2026": {"run-1": stale_local}}

    class FakeDoc:
        exists = True

        def to_dict(self):
            return fresh_remote.model_dump(mode="json")

    class FakeRunDoc:
        def get(self):
            return FakeDoc()

    class FakeRunsCollection:
        def document(self, run_id: str):
            assert run_id == "run-1"
            return FakeRunDoc()

    class FakeRaceDoc:
        def collection(self, name: str):
            assert name == "runs"
            return FakeRunsCollection()

    class FakeCollection:
        def document(self, race_id: str):
            assert race_id == "ga-senate-2026"
            return FakeRaceDoc()

    class FakeDb:
        def collection(self, name: str):
            assert name == "races"
            return FakeCollection()

    manager._db = FakeDb()

    result = manager.get_run("ga-senate-2026", "run-1")

    assert result is not None
    assert result.status == RunStatus.CANCELLED
