"""Tests for run_health persistence on RunInfo/RunManager and backward compatibility.

A run's `run_health` is a separate, definitive "did this actually succeed"
verdict from its `status` — see shared/run_health.py. These tests check that:
  * complete_run/fail_run/cancel_run attach it to the persisted RunInfo,
  * RunStep.failure_reasons is populated by update_step_status,
  * legacy run records (dicts with no run_health/failure_reasons keys at all)
    still deserialize into RunInfo without raising.
"""

from pipeline_client.backend.models import RunInfo, RunRequest, RunStatus, RunStep
from pipeline_client.backend.run_manager import RunManager
from shared.run_health import RunFailureReason, RunHealthStatus, RunHealthVerdict


def _new_manager() -> RunManager:
    manager = RunManager()
    manager._db = None  # force in-memory local-dev mode; no real Firestore needed
    return manager


def test_complete_run_persists_run_health():
    manager = _new_manager()
    request = RunRequest(payload={"race_id": "ga-senate-2026"})
    run_info = manager.create_run(["discovery"], request)

    run_health = RunHealthVerdict(status=RunHealthStatus.DEGRADED, reasons=[RunFailureReason.STEP_NO_DATA])
    result = manager.complete_run(run_info.run_id, run_health=run_health)

    assert result is not None
    assert result.status == RunStatus.COMPLETED  # status stays "completed" ...
    assert result.run_health.status == RunHealthStatus.DEGRADED  # ... even though health is degraded
    assert result.run_health.reasons == [RunFailureReason.STEP_NO_DATA]


def test_complete_run_without_run_health_leaves_it_none():
    """Backward compat: existing call sites that don't pass run_health still work."""
    manager = _new_manager()
    request = RunRequest(payload={"race_id": "ga-senate-2026"})
    run_info = manager.create_run(["discovery"], request)

    result = manager.complete_run(run_info.run_id)

    assert result is not None
    assert result.run_health is None


def test_fail_run_persists_run_health():
    manager = _new_manager()
    request = RunRequest(payload={"race_id": "ga-senate-2026"})
    run_info = manager.create_run(["discovery"], request)

    run_health = {
        "status": "failed",
        "reasons": ["provider_auth_failure"],
        "step_failures": [],
        "summary": "OpenRouter key exhausted",
    }
    result = manager.fail_run(run_info.run_id, "OpenRouter 403", run_health=run_health)

    assert result is not None
    assert result.status == RunStatus.FAILED
    assert result.run_health.status == RunHealthStatus.FAILED
    assert result.run_health.reasons == [RunFailureReason.PROVIDER_AUTH_FAILURE]


def test_cancel_run_sets_cancelled_run_health():
    manager = _new_manager()
    request = RunRequest(payload={"race_id": "ga-senate-2026"})
    run_info = manager.create_run(["discovery"], request)

    result = manager.cancel_run(run_info.run_id)

    assert result is not None
    assert result.status == RunStatus.CANCELLED
    assert result.run_health.status == RunHealthStatus.FAILED
    assert result.run_health.reasons == [RunFailureReason.CANCELLED]


def test_update_step_status_persists_failure_reasons():
    manager = _new_manager()
    request = RunRequest(payload={"race_id": "ga-senate-2026"})
    run_info = manager.create_run(["finance"], request)

    manager.update_step_status(
        run_info.run_id,
        "finance",
        RunStatus.COMPLETED,
        failure_reasons=[RunFailureReason.STEP_NO_DATA],
    )

    step = next(s for s in manager.active_runs[run_info.run_id].steps if s.name == "finance")
    assert step.failure_reasons == [RunFailureReason.STEP_NO_DATA]


def test_update_step_status_defaults_failure_reasons_empty():
    manager = _new_manager()
    request = RunRequest(payload={"race_id": "ga-senate-2026"})
    run_info = manager.create_run(["discovery"], request)

    manager.update_step_status(run_info.run_id, "discovery", RunStatus.COMPLETED)

    step = next(s for s in manager.active_runs[run_info.run_id].steps if s.name == "discovery")
    assert step.failure_reasons == []


# ---------------------------------------------------------------------------
# Backward compatibility: legacy Firestore docs lack run_health/failure_reasons
# ---------------------------------------------------------------------------


def test_run_info_deserializes_legacy_doc_without_run_health():
    legacy_doc = {
        "run_id": "legacy-run",
        "status": "completed",
        "payload": {"race_id": "ga-senate-2026"},
        "options": {},
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:10:00+00:00",
        "steps": [
            {"name": "discovery", "status": "completed"},
        ],
    }

    run_info = RunInfo(**legacy_doc)

    assert run_info.run_health is None
    assert run_info.steps[0].failure_reasons == []


def test_run_info_round_trips_run_health_through_json_dump():
    run_info = RunInfo(
        run_id="r1",
        status=RunStatus.COMPLETED,
        payload={"race_id": "ga-senate-2026"},
        options={},
        started_at="2026-01-01T00:00:00+00:00",
        run_health=RunHealthVerdict(status=RunHealthStatus.DEGRADED, reasons=[RunFailureReason.PLACEHOLDER_CONTENT]),
    )

    dumped = run_info.model_dump(mode="json")
    assert dumped["run_health"]["status"] == "degraded"
    assert dumped["run_health"]["reasons"] == ["placeholder_content"]

    # And it must load back cleanly, as if freshly read from Firestore.
    reloaded = RunInfo(**dumped)
    assert reloaded.run_health.status == RunHealthStatus.DEGRADED
