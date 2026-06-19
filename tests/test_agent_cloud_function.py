"""Tests for the agent Cloud Function entry point (functions/agent/main.py)."""

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

# Stub functions_framework so the CF module can import without the package installed
if "functions_framework" not in sys.modules:
    _ff_stub = MagicMock()
    _ff_stub.cloud_event = staticmethod(lambda f: f)  # pass-through decorator
    sys.modules["functions_framework"] = _ff_stub

# Stub cloudevents so the CF module can import without the package installed
if "cloudevents" not in sys.modules:
    _ce_pkg = MagicMock()
    _ce_http = MagicMock()
    _ce_http.CloudEvent = MagicMock
    sys.modules["cloudevents"] = _ce_pkg
    sys.modules["cloudevents.http"] = _ce_http


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cloud_event(item_id: str) -> MagicMock:
    """Build a minimal CloudEvent mock that matches Eventarc Firestore format."""
    ev = MagicMock()
    subject = f"projects/test-proj/databases/(default)/documents/pipeline_queue/{item_id}"
    ev.get.side_effect = lambda key, default=None: subject if key == "subject" else default
    return ev


def _make_firestore_mock(*, item_data: dict | None = None, run_exists: bool = False):
    """Return a mock Firestore client pre-configured for common CF paths."""
    db = MagicMock()
    queue_state = dict(item_data or {})

    # pipeline_queue doc
    queue_doc = MagicMock()
    queue_doc.exists = item_data is not None
    queue_doc.to_dict.side_effect = lambda: dict(queue_state)

    item_ref = MagicMock()
    item_ref.get.return_value = queue_doc
    item_ref.update.side_effect = lambda update: queue_state.update(update)

    # pipeline_runs doc
    run_doc = MagicMock()
    run_doc.exists = run_exists
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    # races doc
    race_ref = MagicMock()
    race_doc = MagicMock()
    race_doc.exists = item_data is not None
    race_doc.to_dict.return_value = {
        "current_run_id": (item_data or {}).get("run_id"),
        "status": "running",
    }
    race_ref.get.return_value = race_doc

    def _collection(name):
        coll = MagicMock()
        if name == "pipeline_queue":
            coll.document.return_value = item_ref
        elif name == "pipeline_runs":
            coll.document.return_value = run_ref
        elif name == "races":
            coll.document.return_value = race_ref
        return coll

    db.collection.side_effect = _collection

    # Firestore transaction: run_transaction calls callback(transaction, item_ref)
    # and returns the result.
    def _run_transaction(callback, *args):
        tx = MagicMock()
        return callback(tx, *args)

    db.run_transaction.side_effect = _run_transaction
    transaction = MagicMock()

    def _transaction_update(ref, update):
        if ref is item_ref:
            queue_state.update(update)

    transaction.update.side_effect = _transaction_update
    db.transaction.return_value = transaction

    return db, item_ref, run_ref, race_ref


# ---------------------------------------------------------------------------
# Unit: subject parsing
# ---------------------------------------------------------------------------


def test_skips_when_subject_unparseable(caplog):
    """Returns early if the subject path cannot be parsed."""
    import functions.agent.main as cf_main  # noqa: F401

    ev = MagicMock()
    ev.get.return_value = ""  # empty subject

    with patch("functions.agent.main._get_fs") as mock_fs:
        cf_main.process_queue_item(ev)
        mock_fs.assert_not_called()


# ---------------------------------------------------------------------------
# Unit: item not found / already claimed
# ---------------------------------------------------------------------------


def test_skips_when_item_already_running():
    """Returns early without processing if item status is not 'pending'."""
    import functions.agent.main as cf_main

    already_running = {
        "race_id": "az-01-senate-2026",
        "status": "running",
        "run_id": "run-xyz",
        "options": {},
        "lease_owner": "other-worker",
        "lease_expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=already_running)

    ev = _make_cloud_event("item-001")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
    ):
        with pytest.raises(RuntimeError, match="active lease"):
            cf_main.process_queue_item(ev)
        mock_run.assert_not_called()


def test_reclaims_running_item_after_lease_expiry():
    import functions.agent.main as cf_main

    expired = {
        "race_id": "az-01-senate-2026",
        "status": "running",
        "run_id": "run-expired",
        "options": {},
        "lease_owner": "dead-worker",
        "lease_expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    db, item_ref, _run_ref, _race_ref = _make_firestore_mock(item_data=expired)

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
    ):
        cf_main.process_queue_item(_make_cloud_event("item-expired"))

    mock_run.assert_called_once()
    claim_updates = [call.args[1] for call in db.transaction.return_value.update.call_args_list]
    claim = next(update for update in claim_updates if update.get("status") == "running")
    assert claim["lease_owner"] != "dead-worker"
    assert "recovered_at" in claim
    assert claim["lease_expires_at"] > datetime.now(timezone.utc)


def test_terminal_retry_is_acknowledged_without_rerunning():
    import functions.agent.main as cf_main

    completed = {
        "race_id": "az-01-senate-2026",
        "status": "completed",
        "run_id": "run-completed",
        "options": {},
    }
    db, _item_ref, _run_ref, _race_ref = _make_firestore_mock(item_data=completed)

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
    ):
        cf_main.process_queue_item(_make_cloud_event("item-completed"))

    mock_run.assert_not_called()


def test_skips_when_item_missing():
    """Returns early when queue document does not exist."""
    import functions.agent.main as cf_main

    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=None)

    ev = _make_cloud_event("item-missing")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
    ):
        cf_main.process_queue_item(ev)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Unit: missing race_id
# ---------------------------------------------------------------------------


def test_marks_failed_when_race_id_missing():
    """Marks item as failed immediately if queue doc has no race_id."""
    import functions.agent.main as cf_main

    bad_item = {"status": "pending", "race_id": "", "run_id": "run-bad", "options": {}}
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=bad_item)

    ev = _make_cloud_event("item-no-race")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
    ):
        cf_main.process_queue_item(ev)
        mock_run.assert_not_called()

    # Should update item with failed status
    item_ref.update.assert_called_once()
    args = item_ref.update.call_args[0][0]
    assert args["status"] == "failed"
    assert args["ttl_at"] > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Unit: successful completion
# ---------------------------------------------------------------------------


def test_marks_completed_on_success():
    """On normal completion, item and run are marked completed; race is set to draft."""
    import functions.agent.main as cf_main

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-ok",
        "options": {"cheap_mode": True},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    ev = _make_cloud_event("item-ok")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent"),  # no-op success
    ):
        cf_main.process_queue_item(ev)

    # item_ref.update called with completed status
    update_calls = [c[0][0] for c in item_ref.update.call_args_list]
    statuses = [u.get("status") for u in update_calls]
    assert "completed" in statuses, f"Expected 'completed' in {statuses}"
    completed_update = next(u for u in update_calls if u.get("status") == "completed")
    assert completed_update["ttl_at"] > datetime.now(timezone.utc)

    # races doc updated with draft and run summary metadata
    race_set_calls = [c[0][0] for c in race_ref.set.call_args_list]
    final_update = next(u for u in race_set_calls if u.get("status") == "draft")
    assert final_update["current_run_id"] is None
    assert final_update["last_run_id"] == "run-ok"
    assert final_update["last_run_status"] == "completed"
    assert "last_run_at" in final_update
    assert "total_runs" in final_update


# ---------------------------------------------------------------------------
# Unit: failure path
# ---------------------------------------------------------------------------


def test_marks_failed_on_exception():
    """On unhandled exception from _run_agent, item and run are marked failed."""
    import functions.agent.main as cf_main

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-fail",
        "options": {},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    ev = _make_cloud_event("item-fail")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent", side_effect=RuntimeError("boom")),
    ):
        cf_main.process_queue_item(ev)

    update_calls = [c[0][0] for c in item_ref.update.call_args_list]
    statuses = [u.get("status") for u in update_calls]
    assert "failed" in statuses, f"Expected 'failed' in {statuses}"
    failed_update = next(u for u in update_calls if u.get("status") == "failed")
    assert failed_update["ttl_at"] > datetime.now(timezone.utc)

    # Error message should be recorded
    errors = [u.get("error") for u in update_calls if u.get("status") == "failed"]
    assert any("boom" in (e or "") for e in errors)

    race_set_calls = [c[0][0] for c in race_ref.set.call_args_list]
    final_update = next(u for u in race_set_calls if u.get("status") == "failed")
    assert final_update["current_run_id"] is None
    assert final_update["last_run_id"] == "run-fail"
    assert final_update["last_run_status"] == "failed"
    assert "last_run_at" in final_update
    assert "total_runs" in final_update


def test_marks_cancelled_on_agent_cancelled():
    """A handler cancellation should not be converted into a failed run."""
    import functions.agent.main as cf_main
    from functions.agent.main import _CancelledExit

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-cancel",
        "options": {},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    ev = _make_cloud_event("item-cancel")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent", side_effect=_CancelledExit("cancelled by admin")),
    ):
        cf_main.process_queue_item(ev)

    item_updates = [c[0][0] for c in item_ref.update.call_args_list]
    run_updates = [c[0][0] for c in run_ref.update.call_args_list]
    race_sets = [c[0][0] for c in race_ref.set.call_args_list]

    assert any(update.get("status") == "cancelled" for update in item_updates)
    cancelled_update = next(update for update in item_updates if update.get("status") == "cancelled")
    assert cancelled_update["ttl_at"] > datetime.now(timezone.utc)
    assert any(update.get("status") == "cancelled" for update in run_updates)
    assert any(update.get("status") == "cancelled" for update in race_sets)
    assert any(update.get("status") == "cancelled" and update.get("current_run_id") is None for update in race_sets)


def test_cancelled_run_does_not_overwrite_new_current_run():
    """A late cancellation from an old invocation must not clobber a newly queued run."""
    import functions.agent.main as cf_main
    from functions.agent.main import _CancelledExit

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-old",
        "options": {},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    race_doc = MagicMock()
    race_doc.exists = True
    race_doc.to_dict.return_value = {"status": "queued", "current_run_id": "run-new"}
    race_ref.get.return_value = race_doc

    ev = _make_cloud_event("item-old")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent", side_effect=_CancelledExit("cancelled by admin")),
    ):
        cf_main.process_queue_item(ev)

    race_sets = [c[0][0] for c in race_ref.set.call_args_list]
    assert any(update.get("status") == "running" and update.get("current_run_id") == "run-old" for update in race_sets)
    assert not any(update.get("status") == "cancelled" for update in race_sets)


def test_passes_queue_item_id_to_agent_options():
    """AgentHandler must receive queue_item_id so it can observe admin cancellation."""
    import functions.agent.main as cf_main

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-ok",
        "options": {"cheap_mode": True},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    ev = _make_cloud_event("item-ok")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
    ):
        cf_main.process_queue_item(ev)

    options = mock_run.call_args.args[2]
    assert options["run_id"] == "run-ok"
    assert options["queue_item_id"] == "item-ok"


def test_processes_multiple_queue_items_with_isolated_run_ids():
    """Separate Eventarc queue items should initialise and execute separate runs."""
    import functions.agent.main as cf_main

    item_data_by_id = {
        "item-az": {
            "status": "pending",
            "race_id": "az-senate-2026",
            "run_id": "run-az",
            "options": {"cheap_mode": True},
        },
        "item-ga": {
            "status": "pending",
            "race_id": "ga-governor-2026",
            "run_id": "run-ga",
            "options": {"cheap_mode": False},
        },
    }

    item_refs: dict[str, MagicMock] = {}
    run_refs: dict[str, MagicMock] = {}
    race_refs: dict[str, MagicMock] = {}

    def _make_item_ref(item_id: str):
        if item_id not in item_refs:
            doc = MagicMock()
            doc.exists = item_id in item_data_by_id
            doc.to_dict.return_value = dict(item_data_by_id.get(item_id, {}))
            ref = MagicMock()
            ref.get.return_value = doc
            item_refs[item_id] = ref
        return item_refs[item_id]

    def _make_run_ref(run_id: str):
        if run_id not in run_refs:
            doc = MagicMock()
            doc.exists = False
            ref = MagicMock()
            ref.get.return_value = doc
            run_refs[run_id] = ref
        return run_refs[run_id]

    def _make_race_ref(race_id: str):
        if race_id not in race_refs:
            race_refs[race_id] = MagicMock()
        return race_refs[race_id]

    def _collection(name):
        coll = MagicMock()
        if name == "pipeline_queue":
            coll.document.side_effect = _make_item_ref
        elif name == "pipeline_runs":
            coll.document.side_effect = _make_run_ref
        elif name == "races":
            coll.document.side_effect = _make_race_ref
        return coll

    db = MagicMock()
    db.collection.side_effect = _collection

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch("functions.agent.main._run_agent") as mock_run,
        patch("functions.agent.main._queue_item_owned", return_value=True),
    ):
        cf_main.process_queue_item(_make_cloud_event("item-az"))
        cf_main.process_queue_item(_make_cloud_event("item-ga"))

    calls = mock_run.call_args_list
    assert [call.args[0] for call in calls] == ["az-senate-2026", "ga-governor-2026"]
    assert [call.args[1] for call in calls] == ["run-az", "run-ga"]
    assert calls[0].args[2]["queue_item_id"] == "item-az"
    assert calls[1].args[2]["queue_item_id"] == "item-ga"
    assert run_refs["run-az"].set.call_args.args[0]["race_id"] == "az-senate-2026"
    assert run_refs["run-az"].set.call_args.args[0]["payload"] == {"race_id": "az-senate-2026"}
    assert run_refs["run-ga"].set.call_args.args[0]["race_id"] == "ga-governor-2026"
    assert run_refs["run-ga"].set.call_args.args[0]["payload"] == {"race_id": "ga-governor-2026"}
    assert any(
        update.get("status") == "completed" for update in (c.args[0] for c in item_refs["item-az"].update.call_args_list)
    )
    assert any(
        update.get("status") == "completed" for update in (c.args[0] for c in item_refs["item-ga"].update.call_args_list)
    )


# ---------------------------------------------------------------------------
# Unit: handoff / continuation path
# ---------------------------------------------------------------------------


def test_marks_continued_on_handoff():
    """When _run_agent raises _HandoffExit, item is marked 'continued' (not 'failed')."""
    import functions.agent.main as cf_main
    from functions.agent.main import _HandoffExit

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-handoff",
        "options": {"enabled_steps": ["discovery", "issues"]},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    ev = _make_cloud_event("item-handoff")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch(
            "functions.agent.main._run_agent",
            side_effect=_HandoffExit("item-continuation-abc", ["issues"]),
        ),
    ):
        cf_main.process_queue_item(ev)

    update_calls = [c[0][0] for c in item_ref.update.call_args_list]
    statuses = [u.get("status") for u in update_calls]
    assert "continued" in statuses, f"Expected 'continued' in {statuses}"

    continuation_ids = [u.get("continuation_item_id") for u in update_calls if u.get("status") == "continued"]
    assert "item-continuation-abc" in continuation_ids
    continued_update = next(u for u in update_calls if u.get("status") == "continued")
    assert continued_update["ttl_at"] > datetime.now(timezone.utc)


def test_handoff_records_continuation_run_id():
    """A handoff keeps one logical run active across invocations."""
    import functions.agent.main as cf_main
    from functions.agent.main import _HandoffExit

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-handoff",
        "options": {"enabled_steps": ["discovery", "issues"]},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    ev = _make_cloud_event("item-handoff")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch(
            "functions.agent.main._run_agent",
            side_effect=_HandoffExit("item-continuation-abc", ["issues"], "run-handoff"),
        ),
    ):
        cf_main.process_queue_item(ev)

    run_updates = [c[0][0] for c in run_ref.update.call_args_list]
    handoff_updates = [u for u in run_updates if u.get("continuation_item_id") == "item-continuation-abc"]
    assert handoff_updates
    assert handoff_updates[-1]["status"] == "running"
    assert handoff_updates[-1]["continuation_run_id"] == "run-handoff"

    race_sets = [c[0][0] for c in race_ref.set.call_args_list]
    assert any(update.get("status") == "queued" and update.get("current_run_id") == "run-handoff" for update in race_sets)


def test_handoff_does_not_requeue_if_item_was_cancelled_during_run():
    """Late handoff from a cancelled invocation must not overwrite race state."""
    import functions.agent.main as cf_main
    from functions.agent.main import _HandoffExit

    item_data = {
        "status": "pending",
        "race_id": "az-01-senate-2026",
        "run_id": "run-handoff-cancelled",
        "options": {"enabled_steps": ["discovery", "issues"]},
    }
    db, item_ref, run_ref, race_ref = _make_firestore_mock(item_data=item_data)

    pending_doc = MagicMock()
    pending_doc.exists = True
    pending_doc.to_dict.return_value = item_data
    cancelled_doc = MagicMock()
    cancelled_doc.exists = True
    cancelled_doc.to_dict.return_value = {"status": "cancelled"}
    item_ref.get.side_effect = [pending_doc, cancelled_doc]

    continuation_ref = MagicMock()

    def _collection(name):
        coll = MagicMock()
        if name == "pipeline_queue":
            coll.document.side_effect = lambda doc_id: continuation_ref if doc_id == "item-continuation-abc" else item_ref
        elif name == "pipeline_runs":
            coll.document.return_value = run_ref
        elif name == "races":
            coll.document.return_value = race_ref
        return coll

    db.collection.side_effect = _collection
    ev = _make_cloud_event("item-handoff-cancelled")

    with (
        patch("functions.agent.main._get_fs", return_value=db),
        patch(
            "functions.agent.main._run_agent",
            side_effect=_HandoffExit("item-continuation-abc", ["issues"], "run-continuation-xyz"),
        ),
    ):
        cf_main.process_queue_item(ev)

    item_updates = [c.args[0] for c in item_ref.update.call_args_list]
    assert not any(update.get("status") == "continued" for update in item_updates)
    continuation_ref.update.assert_called_once()
    assert continuation_ref.update.call_args.args[0]["status"] == "cancelled"

    race_sets = [c.args[0] for c in race_ref.set.call_args_list]
    assert not any(update.get("current_run_id") == "run-continuation-xyz" for update in race_sets)


# ---------------------------------------------------------------------------
# Unit: _load_gcs_json
# ---------------------------------------------------------------------------


def test_load_gcs_json_returns_none_on_missing_blob():
    """_load_gcs_json returns None for non-existent blobs."""
    import functions.agent.main as cf_main

    mock_blob = MagicMock()
    mock_blob.exists.return_value = False

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_gcs = MagicMock()
    mock_gcs.bucket.return_value = mock_bucket

    with patch("functions.agent.main._get_gcs", return_value=mock_gcs):
        result = cf_main._load_gcs_json("gs://my-bucket/checkpoints/run-xyz.json")

    assert result is None


def test_load_gcs_json_parses_existing_blob():
    """_load_gcs_json fetches and parses JSON from an existing blob."""
    import json

    import functions.agent.main as cf_main

    payload = {"id": "az-01-senate-2026", "candidates": []}
    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = json.dumps(payload)

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_gcs = MagicMock()
    mock_gcs.bucket.return_value = mock_bucket

    with patch("functions.agent.main._get_gcs", return_value=mock_gcs):
        result = cf_main._load_gcs_json("gs://my-bucket/checkpoints/run-xyz.json")

    assert result == payload
