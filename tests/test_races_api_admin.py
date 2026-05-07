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
    assert body["step_details"][0] == {"id": "discovery", "label": "Discovery", "weight": 15}


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
    )

    dumped = opts.model_dump(exclude_none=True)
    assert dumped["save_artifact"] is True
    assert dumped["gemini_model"] == "gemini-test"
    assert dumped["grok_model"] == "grok-test"


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
    """The web dashboard expects /api/races/drafts to return race summary objects."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    draft_json = {
        "id": "az-senate-2026",
        "title": "Arizona Senate 2026",
        "office": "U.S. Senate",
        "jurisdiction": "Arizona",
        "state": "AZ",
        "election_date": "2026-11-03",
        "updated_utc": "2026-05-01T00:00:00Z",
        "candidates": [{"name": "Alice Example", "party": "D", "incumbent": False, "image_url": "https://example.com/a.jpg"}],
    }

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=_build_empty_firestore_mock()),
        patch("gcs_helpers._gcs_list_race_ids", return_value=["az-senate-2026"]),
        patch("gcs_helpers._gcs_get_race_json", return_value=draft_json),
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races/drafts")

    assert resp.status_code == 200
    body = resp.json()
    assert body["races"][0]["id"] == "az-senate-2026"
    assert body["races"][0]["title"] == "Arizona Senate 2026"
    assert body["races"][0]["candidates"][0]["name"] == "Alice Example"


def test_list_races_uses_storage_state_for_draft_flags():
    """Race list should not expose stale Firestore draft metadata as publishable state."""
    os.environ["SKIP_AUTH"] = "true"
    os.environ["ADMIN_API_KEY"] = "test-key"

    import main as app_module

    firestore_helpers._fs_db = None

    stale_doc = _make_existing_doc(
        {
            "race_id": "ga-senate-2026",
            "status": "draft",
            "draft_updated_at": "2026-05-01T00:00:00Z",
            "published_at": "2026-04-01T00:00:00Z",
        }
    )
    active_draft_doc = _make_existing_doc(
        {
            "race_id": "az-senate-2026",
            "status": "published",
            "draft_updated_at": "2026-05-01T00:00:00Z",
            "published_at": "2026-04-01T00:00:00Z",
        }
    )
    coll_races = MagicMock()
    coll_races.limit.return_value = coll_races
    coll_races.stream.return_value = iter([stale_doc, active_draft_doc])
    db = _build_empty_firestore_mock()
    db.collection.side_effect = lambda name: coll_races if name == "races" else MagicMock()

    def _list_ids(prefix):
        return ["az-senate-2026"] if prefix == "drafts" else ["ga-senate-2026", "az-senate-2026"]

    from fastapi.testclient import TestClient

    with (
        patch("firestore_helpers._get_fs", return_value=db),
        patch("gcs_helpers._gcs_list_race_ids", side_effect=_list_ids),
    ):
        tc = TestClient(app_module.app)
        resp = tc.get("/api/races")

    assert resp.status_code == 200
    by_id = {race["race_id"]: race for race in resp.json()["races"]}
    assert by_id["ga-senate-2026"]["status"] == "published"
    assert by_id["ga-senate-2026"]["draft_exists"] is False
    assert by_id["ga-senate-2026"]["published_exists"] is True
    assert by_id["ga-senate-2026"]["draft_updated_at"] is None
    assert by_id["az-senate-2026"]["status"] == "published"
    assert by_id["az-senate-2026"]["draft_exists"] is True
    assert by_id["az-senate-2026"]["published_exists"] is True


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

    race_ref = MagicMock()
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
