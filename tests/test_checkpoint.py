"""Tests for the HandoffTriggered exception and the handoff checkpoint mechanism.

The handoff logic lives inside `AgentHandler.handle()` as a nested closure
(`_on_step_complete` / `_trigger_handoff`).  We test it by:
  1. Verifying the exception class attributes directly.
  2. Exercising the step-tracker callbacks via a specially crafted mock agent
     that calls them with a past deadline so the handoff path triggers.
"""

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline_client.backend.handlers.agent import HandoffTriggered


@pytest.fixture(autouse=True)
def fast_handler_side_effects(monkeypatch, tmp_path):
    """Keep AgentHandler unit tests focused on handoff behavior."""
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.setenv("PIPELINE_METRICS_DB_PATH", str(tmp_path / "pipeline_metrics.db"))
    with (
        patch(
            "pipeline_client.backend.handlers.agent.AgentHandler._load_existing_from_gcs",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("pipeline_client.backend.handlers.agent.AgentHandler._get_storage_client", return_value=None),
        patch("pipeline_client.backend.race_manager.race_manager.update_race_metadata"),
        patch("pipeline_client.backend.pipeline_metrics.get_pipeline_metrics_store") as metrics_store,
    ):
        metrics_store.return_value.record_run = AsyncMock()
        yield


# ---------------------------------------------------------------------------
# Exception class
# ---------------------------------------------------------------------------


def test_handoff_triggered_attributes():
    """HandoffTriggered stores continuation_item_id and remaining_steps."""
    exc = HandoffTriggered("item-abc", ["refinement", "review"])
    assert exc.continuation_item_id == "item-abc"
    assert exc.remaining_steps == ["refinement", "review"]
    assert "item-abc" in str(exc)


def test_handoff_triggered_is_exception():
    assert issubclass(HandoffTriggered, Exception)


# ---------------------------------------------------------------------------
# run_agent mock factory
# ---------------------------------------------------------------------------


def _make_run_agent_calling_tracker(step: str, *, complete: bool = True, race_json: dict | None = None):
    """
    Returns an async mock of run_agent that calls step_tracker callbacks for
    the given step, simulating what the real agent does at runtime.
    """

    async def _fake_run_agent(race_id, *, step_tracker=None, enabled_steps=None, **_kw):
        if step_tracker:
            step_tracker["start"](step)
            if complete:
                kwargs = {"duration_ms": 100}
                if race_json is not None:
                    kwargs["race_json"] = race_json
                step_tracker["complete"](step, **kwargs)
        return {"id": race_id, "candidates": []}

    return _fake_run_agent


def _make_run_agent_calling_progress(step: str):
    async def _fake_run_agent(race_id, *, step_tracker=None, enabled_steps=None, **_kw):
        if step_tracker:
            step_tracker["start"](step)
            step_tracker["progress"](step, pct=25, message="Working")
        return {"id": race_id, "candidates": []}

    return _fake_run_agent


def _make_run_agent_calling_log_after_start(step: str):
    async def _fake_run_agent(race_id, *, on_log=None, step_tracker=None, **_kw):
        if step_tracker:
            step_tracker["start"](step)
        if on_log:
            on_log("info", "deep loop log")
        return {"id": race_id, "candidates": []}

    return _fake_run_agent


@pytest.mark.asyncio
async def test_continuation_uses_checkpoint_payload_instead_of_gcs():
    """Continuation runs must resume from the checkpoint loaded by the Cloud Function."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    checkpoint = {"id": "az-01-senate-2026", "candidates": [{"name": "Alice"}]}

    async def _fake_run_agent(_race_id, *, existing_data=None, **_kw):
        assert existing_data == checkpoint
        return {"id": "az-01-senate-2026", "candidates": [{"name": "Alice"}]}

    with (
        patch("pipeline_client.agent.agent.run_agent", side_effect=_fake_run_agent),
        patch.object(handler, "_load_existing_from_gcs", new_callable=AsyncMock) as mock_load_existing,
        patch.object(handler, "_save_draft", new_callable=AsyncMock, return_value=Path("drafts/az-01-senate-2026.json")),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger", MagicMock()),
    ):
        result = await handler.handle(
            {"race_id": "az-01-senate-2026", "existing_data": checkpoint},
            {"run_id": "run-continuation", "enabled_steps": ["issues"], "force_fresh": True, "is_continuation": True},
        )

    assert result["status"] == "draft"
    mock_load_existing.assert_not_called()


# ---------------------------------------------------------------------------
# Handoff triggered after step completes when deadline has passed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_raised_when_deadline_exceeded():
    """_on_step_complete raises HandoffTriggered when deadline is past and steps remain."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    past_deadline = time.time() - 10.0  # definitely in the past

    options = {
        "run_id": "run-handoff-test",
        "deadline_at": past_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {"race_id": "az-01-senate-2026"}

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set = MagicMock()

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_tracker("discovery"),
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        # FirestoreLogger is imported inside handle() from firestore_logger module
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger", MagicMock()),
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
    ):
        with pytest.raises(HandoffTriggered) as exc_info:
            await handler.handle(payload, options)

    exc = exc_info.value
    # "issues" was not yet completed, so it should be in remaining_steps
    assert "issues" in exc.remaining_steps


@pytest.mark.asyncio
async def test_run_budget_exhaustion_forces_checkpoint_handoff_before_deadline():
    """Deep budget exhaustion should use the existing continuation path immediately."""
    from pipeline_client.agent.run_budget import RunBudgetExceeded
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    future_deadline = time.time() + 300.0
    options = {
        "run_id": "run-budget-handoff-test",
        "deadline_at": future_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {
        "race_id": "az-01-senate-2026",
        "existing_data": {"id": "az-01-senate-2026", "candidates": [{"name": "Alice"}]},
    }
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.set = MagicMock()

    async def _fake_run_agent(_race_id, *, step_tracker=None, run_budget=None, **_kw):
        assert run_budget.deadline_at == future_deadline
        step_tracker["start"]("discovery")
        raise RunBudgetExceeded("not enough time for another provider call")

    with (
        patch("pipeline_client.agent.agent.run_agent", side_effect=_fake_run_agent),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger", MagicMock()),
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
    ):
        with pytest.raises(HandoffTriggered) as exc_info:
            await handler.handle(payload, options)

    assert exc_info.value.remaining_steps == ["discovery", "issues"]


@pytest.mark.asyncio
async def test_handoff_raised_during_step_progress_when_deadline_exceeded():
    """Long steps should hand off on progress, before Cloud Function hard timeout."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    past_deadline = time.time() - 10.0

    options = {
        "run_id": "run-progress-handoff-test",
        "deadline_at": past_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {
        "race_id": "az-01-senate-2026",
        "existing_data": {"id": "az-01-senate-2026", "candidates": [{"name": "Alice"}]},
    }

    queue_doc_ref = MagicMock()
    queue_collection = MagicMock()
    queue_collection.document.return_value = queue_doc_ref
    mock_db = MagicMock()
    mock_db.collection.return_value = queue_collection

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client = MagicMock()
    mock_storage_client.bucket.return_value = mock_bucket

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_progress("discovery"),
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch.object(handler, "_get_storage_client", return_value=mock_storage_client),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
        patch("pipeline_client.backend.settings.settings.gcs_bucket", "test-bucket"),
    ):
        with pytest.raises(HandoffTriggered) as exc_info:
            await handler.handle(payload, options)

    continuation_doc = queue_doc_ref.set.call_args.args[0]
    assert continuation_doc["options"]["enabled_steps"] == ["discovery", "issues"]
    assert "deadline_at" not in continuation_doc["options"]
    assert continuation_doc["existing_data_gcs_path"] == "gs://test-bucket/checkpoints/run-progress-handoff-test.json"
    assert exc_info.value.continuation_run_id == continuation_doc["run_id"]
    mock_fs_logger_cls.return_value.mark_continued.assert_called_with(continuation_doc["run_id"])


@pytest.mark.asyncio
async def test_handoff_raised_during_log_callback_when_deadline_exceeded():
    """Deep log callbacks should also check the handoff deadline."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    options = {
        "run_id": "run-log-handoff-test",
        "deadline_at": 100.0,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {
        "race_id": "az-01-senate-2026",
        "existing_data": {"id": "az-01-senate-2026", "candidates": [{"name": "Alice"}]},
    }

    queue_doc_ref = MagicMock()
    queue_collection = MagicMock()
    queue_collection.document.return_value = queue_doc_ref
    mock_db = MagicMock()
    mock_db.collection.return_value = queue_collection

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client = MagicMock()
    mock_storage_client.bucket.return_value = mock_bucket

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_log_after_start("discovery"),
        ),
        patch("pipeline_client.backend.handlers.agent.time.time", return_value=200.0),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch.object(handler, "_get_storage_client", return_value=mock_storage_client),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
        patch("pipeline_client.backend.settings.settings.gcs_bucket", "test-bucket"),
    ):
        with pytest.raises(HandoffTriggered) as exc_info:
            await handler.handle(payload, options)

    continuation_doc = queue_doc_ref.set.call_args.args[0]
    assert continuation_doc["options"]["enabled_steps"] == ["discovery", "issues"]
    assert continuation_doc["existing_data_gcs_path"] == "gs://test-bucket/checkpoints/run-log-handoff-test.json"
    assert exc_info.value.continuation_run_id == continuation_doc["run_id"]
    mock_fs_logger_cls.return_value.mark_continued.assert_called_with(continuation_doc["run_id"])


@pytest.mark.asyncio
async def test_handoff_writes_continuation_run_and_checkpoint_path():
    """Continuation queue docs must match what the Cloud Function reads."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    past_deadline = time.time() - 10.0
    latest_race_json = {"id": "az-01-senate-2026", "candidates": [{"name": "Alice"}]}

    options = {
        "run_id": "run-handoff-test",
        "deadline_at": past_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {"race_id": "az-01-senate-2026"}

    queue_doc_ref = MagicMock()
    queue_collection = MagicMock()
    queue_collection.document.return_value = queue_doc_ref
    mock_db = MagicMock()
    mock_db.collection.return_value = queue_collection

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client = MagicMock()
    mock_storage_client.bucket.return_value = mock_bucket

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_tracker("discovery", race_json=latest_race_json),
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch.object(handler, "_get_storage_client", return_value=mock_storage_client),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
        patch("pipeline_client.backend.settings.settings.gcs_bucket", "test-bucket"),
    ):
        with pytest.raises(HandoffTriggered) as exc_info:
            await handler.handle(payload, options)

    continuation_doc = queue_doc_ref.set.call_args.args[0]
    assert continuation_doc["race_id"] == "az-01-senate-2026"
    assert continuation_doc["run_id"]
    assert continuation_doc["is_continuation"] is True
    assert continuation_doc["parent_run_id"] == "run-handoff-test"
    assert continuation_doc["existing_data_gcs_path"] == "gs://test-bucket/checkpoints/run-handoff-test.json"
    assert continuation_doc["options"]["enabled_steps"] == ["issues"]
    assert continuation_doc["options"]["force_fresh"] is False
    assert "existing_data_gcs_path" not in continuation_doc["options"]
    assert exc_info.value.continuation_run_id == continuation_doc["run_id"]
    mock_fs_logger_cls.return_value.mark_continued.assert_called_with(continuation_doc["run_id"])
    mock_blob.upload_from_string.assert_called_once()


@pytest.mark.asyncio
async def test_handoff_fails_if_continuation_queue_write_fails():
    """A failed continuation write must not mark the current run as safely continued."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    past_deadline = time.time() - 10.0

    options = {
        "run_id": "run-handoff-test",
        "deadline_at": past_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {"race_id": "az-01-senate-2026"}

    queue_doc_ref = MagicMock()
    queue_doc_ref.set.side_effect = RuntimeError("write failed")
    queue_collection = MagicMock()
    queue_collection.document.return_value = queue_doc_ref
    mock_db = MagicMock()
    mock_db.collection.return_value = queue_collection

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_tracker("discovery"),
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
    ):
        with pytest.raises(RuntimeError, match="Failed to create continuation queue item"):
            await handler.handle(payload, options)

    mock_fs_logger_cls.return_value.mark_continued.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_queue_item_does_not_handoff_after_deadline():
    """A run cancelled just before deadline handoff must not create a continuation."""
    from pipeline_client.backend.handlers.agent import AgentCancelled, AgentHandler

    handler = AgentHandler()
    past_deadline = time.time() - 10.0
    options = {
        "run_id": "run-cancel-before-handoff",
        "queue_item_id": "queue-cancel-before-handoff",
        "deadline_at": past_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {"race_id": "az-01-senate-2026"}

    queue_doc = MagicMock()
    queue_doc.exists = True
    queue_doc.to_dict.return_value = {"status": "cancelled"}
    queue_doc_ref = MagicMock()
    queue_doc_ref.get.return_value = queue_doc
    queue_collection = MagicMock()
    queue_collection.document.return_value = queue_doc_ref
    mock_db = MagicMock()
    mock_db.collection.return_value = queue_collection

    with (
        patch("pipeline_client.agent.agent.run_agent", side_effect=_make_run_agent_calling_tracker("discovery")),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger") as mock_fs_logger_cls,
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
    ):
        with pytest.raises(AgentCancelled):
            await handler.handle(payload, options)

    queue_doc_ref.set.assert_not_called()
    mock_fs_logger_cls.return_value.mark_continued.assert_not_called()


@pytest.mark.asyncio
async def test_no_handoff_when_last_step_completes():
    """No HandoffTriggered when the last enabled step completes past deadline."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    past_deadline = time.time() - 10.0

    # Only one step — after it completes, _remaining is empty, so no handoff
    options = {
        "run_id": "run-no-handoff",
        "deadline_at": past_deadline,
        "enabled_steps": ["discovery"],
    }
    payload = {"race_id": "az-01-senate-2026"}

    mock_db = MagicMock()

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_tracker("discovery"),
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger", MagicMock()),
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
    ):
        # Should NOT raise HandoffTriggered
        result = await handler.handle(payload, options)

    assert result["status"] == "draft"


@pytest.mark.asyncio
async def test_no_handoff_when_deadline_in_future():
    """No HandoffTriggered when steps remain but deadline has not passed."""
    from pipeline_client.backend.handlers.agent import AgentHandler

    handler = AgentHandler()
    future_deadline = time.time() + 9999.0  # far future

    options = {
        "run_id": "run-future-deadline",
        "deadline_at": future_deadline,
        "enabled_steps": ["discovery", "issues"],
    }
    payload = {"race_id": "az-01-senate-2026"}

    mock_db = MagicMock()

    with (
        patch(
            "pipeline_client.agent.agent.run_agent",
            side_effect=_make_run_agent_calling_tracker("discovery"),
        ),
        patch.object(handler, "_save_draft", new_callable=AsyncMock),
        patch("pipeline_client.backend.firestore_logger.FirestoreLogger", MagicMock()),
        patch("pipeline_client.backend.firestore_logger._get_db", return_value=mock_db),
    ):
        result = await handler.handle(payload, options)

    assert result["status"] == "draft"
