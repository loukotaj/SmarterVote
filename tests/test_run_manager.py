"""Behavioral tests for pipeline_client.backend.run_manager.RunManager's local
(in-memory, no Firestore) lifecycle: create/start/complete/fail/cancel/delete,
log buffering, and the Firestore-fallback branches of cancel_run/delete_run/
list_recent_runs.

tests/test_run_manager_firestore_sync.py already covers list_active_runs and
get_run's Firestore-merge paths.
"""

import logging
from dataclasses import replace as dataclass_replace
from datetime import datetime, timedelta, timezone

import pytest

from pipeline_client.backend.models import RunInfo, RunRequest, RunStatus
from pipeline_client.backend.run_manager import RunManager


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_SERVICE", raising=False)
    mgr = RunManager()
    yield mgr
    mgr.shutdown()


def test_create_run_initializes_pending_run_with_steps(manager):
    request = RunRequest(payload={"race_id": "ga-senate-2026"})

    run = manager.create_run(["discovery", "images"], request)

    assert run.status == RunStatus.PENDING
    assert [s.name for s in run.steps] == ["discovery", "images"]
    assert manager.active_runs[run.run_id] is run
    assert run.logs == []


def test_add_step_appends_to_existing_run(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    step = manager.add_step(run.run_id, "images")

    assert step.name == "images"
    assert [s.name for s in manager.active_runs[run.run_id].steps] == ["discovery", "images"]


def test_add_step_unknown_run_returns_none(manager):
    assert manager.add_step("no-such-run", "images") is None


def test_update_step_status_running_sets_started_at(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    manager.update_step_status(run.run_id, "discovery", RunStatus.RUNNING)

    step = manager.active_runs[run.run_id].steps[0]
    assert step.status == RunStatus.RUNNING
    assert step.started_at is not None


def test_update_step_status_completed_sets_terminal_fields(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    manager.update_step_status(
        run.run_id,
        "discovery",
        RunStatus.COMPLETED,
        artifact_id="artifact-1",
        duration_ms=1234,
        prompt_tokens=10,
        completion_tokens=20,
        estimated_usd=0.01,
    )

    step = manager.active_runs[run.run_id].steps[0]
    assert step.status == RunStatus.COMPLETED
    assert step.completed_at is not None
    assert step.duration_ms == 1234
    assert step.artifact_id == "artifact-1"
    assert step.prompt_tokens == 10
    assert step.completion_tokens == 20
    assert step.estimated_usd == 0.01
    # The run-level artifact_id also gets set when a step reports one.
    assert manager.active_runs[run.run_id].artifact_id == "artifact-1"


def test_update_step_status_failed_sanitizes_error(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    manager.update_step_status(run.run_id, "discovery", RunStatus.FAILED, error="token=Bearer secret-token-value failed")

    step = manager.active_runs[run.run_id].steps[0]
    assert step.status == RunStatus.FAILED
    assert "secret-token-value" not in step.error


def test_update_step_status_unknown_run_is_noop(manager):
    manager.update_step_status("no-such-run", "discovery", RunStatus.RUNNING)  # must not raise


def test_start_run_marks_running_and_attaches_logger(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    manager.start_run(run.run_id)

    assert manager.active_runs[run.run_id].status == RunStatus.RUNNING
    assert run.run_id in manager._log_handlers

    manager.detach_run_logger(run.run_id)


def test_start_run_unknown_run_is_noop(manager):
    manager.start_run("no-such-run")  # must not raise


def test_complete_run_moves_to_local_history_and_detaches_logger(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.start_run(run.run_id)

    completed = manager.complete_run(run.run_id, artifact_id="artifact-1", duration_ms=500, serper_calls=3)

    assert completed.status == RunStatus.COMPLETED
    assert completed.serper_calls == 3
    assert run.run_id not in manager.active_runs
    assert run.run_id not in manager._log_handlers
    assert manager._local_history[run.run_id] is completed


def test_complete_run_unknown_run_returns_none(manager):
    assert manager.complete_run("no-such-run") is None


def test_fail_run_sanitizes_error_and_moves_to_history(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.start_run(run.run_id)

    failed = manager.fail_run(run.run_id, "Authorization: Bearer secret-value", duration_ms=100, serper_calls=1)

    assert failed.status == RunStatus.FAILED
    assert "secret-value" not in failed.error
    assert failed.serper_calls == 1
    assert run.run_id not in manager.active_runs


def test_fail_run_unknown_run_returns_none(manager):
    assert manager.fail_run("no-such-run", "error") is None


def test_cancel_run_active_run_marks_cancelled(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.start_run(run.run_id)

    cancelled = manager.cancel_run(run.run_id)

    assert cancelled.status == RunStatus.CANCELLED
    assert run.run_id not in manager.active_runs


def test_cancel_run_falls_back_to_local_history_when_still_pending(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    # Simulate the run having left active_runs already (e.g. crashed) while
    # still recorded as pending/running in local history.
    manager._local_history[run.run_id] = run
    del manager.active_runs[run.run_id]

    cancelled = manager.cancel_run(run.run_id)

    assert cancelled is not None
    assert cancelled.status == RunStatus.CANCELLED


def test_cancel_run_local_history_already_terminal_returns_none(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    del manager.active_runs[run.run_id]
    run.status = RunStatus.COMPLETED
    manager._local_history[run.run_id] = run

    assert manager.cancel_run(run.run_id) is None


def test_cancel_run_not_found_anywhere_returns_none(manager):
    assert manager.cancel_run("no-such-run") is None


def test_cancel_run_firestore_fallback_marks_pending_run_cancelled(manager):
    run = RunInfo(
        run_id="remote-run",
        status=RunStatus.PENDING,
        payload={},
        options={},
        started_at=datetime.now(timezone.utc),
        steps=[],
    )

    class FakeDoc:
        exists = True

        def to_dict(self_inner):
            return run.model_dump(mode="json")

    class FakeDocRef:
        def get(self_inner):
            return FakeDoc()

    class FakeCollection:
        def document(self_inner, run_id):
            return FakeDocRef()

    class FakeDb:
        def collection(self_inner, name):
            return FakeCollection()

    manager._db = FakeDb()

    cancelled = manager.cancel_run("remote-run")

    assert cancelled is not None
    assert cancelled.status == RunStatus.CANCELLED


def test_delete_run_active_run_returns_false(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    assert manager.delete_run(run.run_id) is False


def test_delete_run_local_only_mode_evicts_and_returns_true(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    del manager.active_runs[run.run_id]
    manager._local_history[run.run_id] = run

    assert manager.delete_run(run.run_id) is True
    assert run.run_id not in manager._local_history


def test_delete_run_firestore_mode_deletes_existing_doc(manager):
    calls = []

    class FakeDocRef:
        def get(self_inner):
            return type("D", (), {"exists": True})()

        def delete(self_inner):
            calls.append("deleted")

    class FakeCollection:
        def document(self_inner, run_id):
            return FakeDocRef()

    class FakeDb:
        def collection(self_inner, name):
            return FakeCollection()

    manager._db = FakeDb()

    assert manager.delete_run("some-run") is True
    assert calls == ["deleted"]


def test_delete_run_firestore_mode_missing_doc_returns_false(manager):
    class FakeDocRef:
        def get(self_inner):
            return type("D", (), {"exists": False})()

    class FakeCollection:
        def document(self_inner, run_id):
            return FakeDocRef()

    class FakeDb:
        def collection(self_inner, name):
            return FakeCollection()

    manager._db = FakeDb()

    assert manager.delete_run("some-run") is False


def test_delete_run_firestore_mode_swallows_exceptions(manager):
    class FakeCollection:
        def document(self_inner, run_id):
            raise RuntimeError("firestore unavailable")

    class FakeDb:
        def collection(self_inner, name):
            return FakeCollection()

    manager._db = FakeDb()

    assert manager.delete_run("some-run") is False


def test_get_run_checks_active_then_local_history_then_none(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    assert manager.get_run(run.run_id) is run

    del manager.active_runs[run.run_id]
    manager._local_history[run.run_id] = run
    assert manager.get_run(run.run_id) is run

    del manager._local_history[run.run_id]
    assert manager.get_run("no-such-run") is None


def test_list_active_runs_sorted_newest_first_local_only(manager):
    now = datetime.now(timezone.utc)
    older = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.active_runs[older.run_id].started_at = now - timedelta(minutes=5)
    newer = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.active_runs[newer.run_id].started_at = now

    runs = manager.list_active_runs()

    assert [r.run_id for r in runs] == [newer.run_id, older.run_id]


def test_list_recent_runs_local_mode_combines_active_and_history(manager):
    active = manager.create_run(["discovery"], RunRequest(payload={}))
    completed = manager.create_run(["discovery"], RunRequest(payload={}))
    del manager.active_runs[completed.run_id]
    manager._local_history[completed.run_id] = completed

    runs = manager.list_recent_runs(limit=10)

    ids = {r.run_id for r in runs}
    assert ids == {active.run_id, completed.run_id}


def test_list_recent_runs_respects_limit(manager):
    for _ in range(5):
        manager.create_run(["discovery"], RunRequest(payload={}))

    runs = manager.list_recent_runs(limit=2)

    assert len(runs) == 2


def test_list_recent_runs_firestore_mode_merges_history_docs(manager):
    active = manager.create_run(["discovery"], RunRequest(payload={}))

    history_run = RunInfo(
        run_id="history-run",
        status=RunStatus.COMPLETED,
        payload={},
        options={},
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        steps=[],
    )

    class FakeQuery:
        def order_by(self_inner, *a, **k):
            return self_inner

        def limit(self_inner, n):
            return self_inner

        def stream(self_inner):
            return [type("Doc", (), {"id": "history-run", "to_dict": lambda self2: history_run.model_dump(mode="json")})()]

    class FakeCollection:
        def order_by(self_inner, *a, **k):
            return FakeQuery()

    class FakeDb:
        def collection(self_inner, name):
            return FakeCollection()

    manager._db = FakeDb()

    runs = manager.list_recent_runs(limit=10)

    ids = {r.run_id for r in runs}
    assert ids == {active.run_id, "history-run"}


def test_add_run_log_truncates_oversized_buffer(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.retention = dataclass_replace(manager.retention, run_log_buffer_size=2)

    manager.add_run_log(run.run_id, {"message": "one"})
    manager.add_run_log(run.run_id, {"message": "two"})
    manager.add_run_log(run.run_id, {"message": "three"})

    logs = manager.get_run_logs(run.run_id)
    assert [entry["message"] for entry in logs] == ["two", "three"]
    assert manager.dropped_log_count == 1


def test_add_run_log_truncates_long_messages(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.retention = dataclass_replace(manager.retention, max_log_message_chars=10)

    manager.add_run_log(run.run_id, {"message": "x" * 50})

    logs = manager.get_run_logs(run.run_id)
    # max_chars=10 is shorter than the "... [truncated to N chars]" marker
    # itself, so truncate_log_message falls back to a hard cut with no marker.
    assert logs[0]["message"] == "x" * 10
    assert manager.truncated_log_count == 1


def test_add_run_log_unknown_run_is_noop(manager):
    manager.add_run_log("no-such-run", {"message": "hi"})  # must not raise


def test_get_run_logs_returns_empty_list_for_missing_run(manager):
    assert manager.get_run_logs("no-such-run") == []


def test_attach_run_logger_is_idempotent(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))

    manager.attach_run_logger(run.run_id)
    first_handler = manager._log_handlers[run.run_id]
    manager.attach_run_logger(run.run_id)  # second call should be a no-op

    assert manager._log_handlers[run.run_id] is first_handler

    manager.detach_run_logger(run.run_id)


def test_detach_run_logger_unknown_run_is_noop(manager):
    manager.detach_run_logger("no-such-run")  # must not raise


def test_run_log_handler_emit_forwards_to_add_run_log(manager):
    run = manager.create_run(["discovery"], RunRequest(payload={}))
    manager.attach_run_logger(run.run_id)

    test_logger = logging.getLogger("pipeline")
    test_logger.error("something went wrong")

    logs = manager.get_run_logs(run.run_id)
    assert any("something went wrong" in entry["message"] for entry in logs)

    manager.detach_run_logger(run.run_id)
