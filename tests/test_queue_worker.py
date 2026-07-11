"""Tests for the local-worker queue processor (no-handoff execution)."""

import time
from unittest.mock import MagicMock, patch

import pytest


def _fs_mock(item_data: dict):
    """Minimal Firestore mock for worker queue and race state."""
    db = MagicMock()
    state = dict(item_data)

    queue_doc = MagicMock()
    queue_doc.exists = True
    queue_doc.to_dict.side_effect = lambda: dict(state)
    item_ref = MagicMock()
    item_ref.get.return_value = queue_doc
    item_ref.update.side_effect = lambda u: state.update(u)

    run_doc = MagicMock()
    run_doc.exists = False
    run_ref = MagicMock()
    run_ref.get.return_value = run_doc

    race_ref = MagicMock()
    race_doc = MagicMock()
    race_doc.exists = True
    race_doc.to_dict.return_value = {"current_run_id": item_data.get("run_id"), "status": "running"}
    race_ref.get.return_value = race_doc

    def _collection(name):
        coll = MagicMock()
        coll.document.return_value = {"pipeline_queue": item_ref, "pipeline_runs": run_ref, "races": race_ref}[name]
        return coll

    db.collection.side_effect = _collection

    transaction = MagicMock()

    def _tx_update(ref, update):
        if ref is item_ref:
            state.update(update)

    transaction.update.side_effect = _tx_update
    db.transaction.return_value = transaction

    return db, item_ref, run_ref, race_ref


@pytest.mark.asyncio
async def test_process_uses_far_future_deadline_and_completes():
    """The worker must run with a far-future deadline (so no handoff) and finalize."""
    from pipeline_client.backend import queue_processor as qp

    item = {"race_id": "ca-house-01-2026", "run_id": "run-1", "options": {"cheap_mode": True}}
    db, item_ref, run_ref, race_ref = _fs_mock(item)
    captured = {}

    async def fake_run(race_id, run_id, options, existing_data):
        captured["options"] = dict(options)

    with patch.object(qp, "_run_agent", side_effect=fake_run):
        await qp.process_claimed_item(db, MagicMock(), "bucket", "item-1", item, "owner-1")

    # Far-future deadline means _maybe_handoff/PipelineWorkRemaining never fire.
    assert captured["options"]["deadline_at"] > time.time() + 3600
    assert captured["options"]["run_id"] == "run-1"
    assert captured["options"]["queue_item_id"] == "item-1"

    item_updates = [c.args[0] for c in item_ref.update.call_args_list]
    assert any(u.get("status") == "completed" for u in item_updates)
    race_sets = [c.args[0] for c in race_ref.set.call_args_list]
    assert any(u.get("status") == "draft" and u.get("current_run_id") is None for u in race_sets)


@pytest.mark.asyncio
async def test_process_marks_failed_on_agent_error():
    from pipeline_client.backend import queue_processor as qp

    item = {"race_id": "ca-house-01-2026", "run_id": "run-2", "options": {}}
    db, item_ref, run_ref, race_ref = _fs_mock(item)

    async def boom(*_a):
        raise RuntimeError("boom")

    with patch.object(qp, "_run_agent", side_effect=boom):
        await qp.process_claimed_item(db, MagicMock(), "bucket", "item-2", item, "owner-2")

    item_updates = [c.args[0] for c in item_ref.update.call_args_list]
    failed = [u for u in item_updates if u.get("status") == "failed"]
    assert failed and "boom" in (failed[-1].get("error") or "")


def test_claim_local_item_claims_pending_local():
    from pipeline_client.backend import queue_processor as qp

    item = {"status": "pending", "runner": "local", "race_id": "x", "run_id": "r"}
    db, item_ref, _run_ref, _race_ref = _fs_mock(item)

    claimed = qp.claim_local_item(db, item_ref, "owner-1")

    assert claimed is not None
    claim_updates = [c.args[1] for c in db.transaction.return_value.update.call_args_list]
    assert any(u.get("status") == "running" and u.get("lease_owner") == "owner-1" for u in claim_updates)


def test_claim_local_item_skips_non_local():
    from pipeline_client.backend import queue_processor as qp

    item = {"status": "pending", "runner": "cloud_run", "race_id": "x", "run_id": "r"}
    db, item_ref, _run_ref, _race_ref = _fs_mock(item)

    assert qp.claim_local_item(db, item_ref, "owner-1") is None
    claim_updates = [c.args[1] for c in db.transaction.return_value.update.call_args_list]
    assert not any(u.get("status") == "running" for u in claim_updates)


def test_claim_item_supports_cloud_run_runner():
    from pipeline_client.backend import queue_processor as qp

    item = {"status": "pending", "runner": "cloud_run", "race_id": "x", "run_id": "r"}
    db, item_ref, _run_ref, _race_ref = _fs_mock(item)

    assert qp.claim_item(db, item_ref, "job-owner", "cloud_run") is not None


def test_pending_items_filters_runner_and_status_in_firestore():
    from pipeline_client import worker

    db = MagicMock()
    query = MagicMock()
    db.collection.return_value = query
    query.where.return_value = query
    query.limit.return_value = query
    query.stream.return_value = []

    assert worker._pending_items(db, "local", limit=2) == []
    filters = [call.kwargs["filter"] for call in query.where.call_args_list]
    assert [(flt.field_path, flt.op_string, flt.value) for flt in filters] == [
        ("runner", "==", "local"),
        ("status", "==", "pending"),
    ]
