"""Cost-free admin workflow coverage using only in-memory service doubles."""

import pathlib
import sys
from unittest.mock import MagicMock, patch

RACES_API_DIR = pathlib.Path(__file__).parents[2] / "services" / "races-api"
if str(RACES_API_DIR) not in sys.path:
    sys.path.insert(0, str(RACES_API_DIR))

import firestore_helpers  # noqa: E402


def _snapshot(data: dict | None) -> MagicMock:
    snapshot = MagicMock()
    snapshot.exists = data is not None
    snapshot.to_dict.return_value = dict(data or {})
    return snapshot


def test_admin_queue_failure_retry_and_publish_is_local_only(monkeypatch):
    """Exercise the operational happy path without cloud or provider calls."""
    monkeypatch.setenv("SKIP_AUTH", "true")
    monkeypatch.setenv("PIPELINE_DEFAULT_RUNNER", "local")
    race_id = "az-senate-2026"
    race_state: dict = {}
    queue_items: list[dict] = []

    race_ref = MagicMock()
    race_ref.get.side_effect = lambda: _snapshot(race_state or None)

    def queue_ref_for(_item_id: str) -> MagicMock:
        ref = MagicMock()
        ref.set.side_effect = lambda item: queue_items.append(dict(item))
        return ref

    races = MagicMock()
    races.document.side_effect = lambda requested_id: race_ref if requested_id == race_id else MagicMock()
    queue = MagicMock()
    queue.document.side_effect = queue_ref_for
    db = MagicMock()
    db.collection.side_effect = lambda name: races if name == "races" else queue

    def update_race(_race_id: str, update: dict) -> None:
        assert _race_id == race_id
        race_state.update(update)

    draft = {
        "race_id": race_id,
        "title": "Arizona Senate 2026",
        "updated_utc": "2026-07-18T00:00:00+00:00",
        "candidates": [{"name": "Example Candidate"}],
        "pipeline_state": {"status": "complete"},
        "validation": {"grade": "A"},
    }

    import main as app_module
    from fastapi.testclient import TestClient

    firestore_helpers._fs_db = None
    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("firestore_helpers._fs_update_race", side_effect=update_race),
        patch("firestore_helpers._fs_build_published_catalog_fields", return_value={"published_candidate_count": 1}),
        patch("gcs_helpers._gcs_get_race_json", return_value=draft),
        patch("gcs_helpers._publish_race_gcs") as publish,
        patch("gcs_helpers.update_gcs_summaries_json") as update_summaries,
        patch("routers.races_admin._assert_publishable_race"),
    ):
        client = TestClient(app_module.app)

        queued = client.post(
            "/api/races/queue",
            json={"race_ids": [race_id], "options": {"runner": "local", "cheap_mode": True}},
        )
        assert queued.status_code == 200
        assert queued.json()["added"][0]["runner"] == "local"
        assert race_state["status"] == "queued"
        assert queue_items[-1]["runner"] == "local"

        # The worker boundary is simulated: no model or cloud job runs here.
        race_state.update({"status": "failed", "current_run_id": None, "last_run_status": "failed"})

        retried = client.post(f"/api/races/{race_id}/run", json={"runner": "local", "cheap_mode": True})
        assert retried.status_code == 200
        assert retried.json()["runner"] == "local"
        assert race_state["status"] == "queued"
        assert len(queue_items) == 2

        published = client.post(f"/api/races/{race_id}/publish")
        assert published.status_code == 200
        assert race_state["status"] == "published"
        assert race_state["current_run_id"] is None
        publish.assert_called_once_with(race_id, draft)
        update_summaries.assert_called_once_with({race_id: draft})
