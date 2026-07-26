"""Behavioral tests for pipeline_client.backend.pipeline_runner.run_step_async.

This is the core step-execution orchestrator (logging, artifact save, run and
race record updates, metrics) and previously had zero direct test coverage
(13%). All collaborators (run_manager, race_manager, logging_manager, the
step handler, and storage) are replaced with lightweight fakes/mocks so the
test targets pipeline_runner's own control flow, not its dependencies.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import pipeline_client.backend.pipeline_runner as pipeline_runner
from pipeline_client.backend.models import RunRequest, RunStatus


def _fake_logging_manager():
    manager = MagicMock()
    manager._main_loop = None  # short-circuits _safe_broadcast's scheduling path
    manager.setup_logger = MagicMock(return_value=MagicMock())
    manager.send_run_status = AsyncMock()
    return manager


def _fake_run_manager(run_id="run-1", existing_run=None):
    manager = MagicMock()
    manager.create_run = MagicMock(return_value=MagicMock(run_id=run_id))
    manager.get_run = MagicMock(return_value=existing_run)
    manager.start_run = MagicMock()
    manager.update_step_status = MagicMock()
    manager.complete_run = MagicMock()
    manager.fail_run = MagicMock()
    return manager


def _fake_race_manager():
    manager = MagicMock()
    manager.complete_run = MagicMock()
    manager.fail_run = MagicMock()
    return manager


@pytest.mark.asyncio
async def test_run_step_async_happy_path_completes_run_and_race(monkeypatch):
    fake_run_mgr = _fake_run_manager()
    fake_race_mgr = _fake_race_manager()
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)
    monkeypatch.setattr(pipeline_runner, "race_manager", fake_race_mgr)

    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value={"race_json": {"agent_metrics": {"serper_calls": 3}}})
    monkeypatch.setattr(pipeline_runner, "get_handler", MagicMock(return_value=fake_handler))
    monkeypatch.setattr(pipeline_runner, "new_artifact_id", MagicMock(return_value="artifact-123"))
    monkeypatch.setattr(pipeline_runner, "save_artifact", MagicMock(return_value="path/artifact-123.json"))

    request = RunRequest(payload={"race_id": "test-race"})
    result = await pipeline_runner.run_step_async("agent", request)

    assert result.ok is True
    assert result.artifact_id == "artifact-123"
    fake_run_mgr.create_run.assert_called_once()
    fake_run_mgr.start_run.assert_called_once_with("run-1")
    fake_run_mgr.update_step_status.assert_any_call("run-1", "agent", RunStatus.RUNNING)
    fake_run_mgr.complete_run.assert_called_once()
    assert fake_run_mgr.complete_run.call_args.kwargs["serper_calls"] == 3
    fake_race_mgr.complete_run.assert_called_once_with("test-race", "run-1", "artifact-123")
    fake_race_mgr.fail_run.assert_not_called()


@pytest.mark.asyncio
async def test_run_step_async_with_existing_run_id_starts_without_creating(monkeypatch):
    fake_run_mgr = _fake_run_manager(existing_run=MagicMock())
    fake_race_mgr = _fake_race_manager()
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)
    monkeypatch.setattr(pipeline_runner, "race_manager", fake_race_mgr)

    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(pipeline_runner, "get_handler", MagicMock(return_value=fake_handler))
    monkeypatch.setattr(pipeline_runner, "new_artifact_id", MagicMock(return_value="artifact-1"))
    monkeypatch.setattr(pipeline_runner, "save_artifact", MagicMock(return_value="path"))

    request = RunRequest(payload={"race_id": "test-race"})
    result = await pipeline_runner.run_step_async("agent", request, run_id="existing-run-id")

    assert result.ok is True
    fake_run_mgr.create_run.assert_not_called()
    fake_run_mgr.start_run.assert_called_once_with("existing-run-id")


@pytest.mark.asyncio
async def test_run_step_async_raises_when_run_id_not_found(monkeypatch):
    fake_run_mgr = _fake_run_manager(existing_run=None)
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)

    request = RunRequest(payload={"race_id": "test-race"})

    with pytest.raises(ValueError, match="Run not found"):
        await pipeline_runner.run_step_async("agent", request, run_id="missing-run-id")


@pytest.mark.asyncio
async def test_run_step_async_handler_failure_fails_run_and_race(monkeypatch):
    fake_run_mgr = _fake_run_manager()
    fake_race_mgr = _fake_race_manager()
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)
    monkeypatch.setattr(pipeline_runner, "race_manager", fake_race_mgr)

    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(side_effect=RuntimeError("agent exploded"))
    monkeypatch.setattr(pipeline_runner, "get_handler", MagicMock(return_value=fake_handler))

    fake_metrics_store = MagicMock()
    fake_metrics_store.record_run = AsyncMock()
    monkeypatch.setattr(
        "pipeline_client.backend.pipeline_metrics.get_pipeline_metrics_store",
        MagicMock(return_value=fake_metrics_store),
    )

    request = RunRequest(payload={"race_id": "test-race"})
    result = await pipeline_runner.run_step_async("agent", request)

    assert result.ok is False
    assert "agent exploded" in result.error
    fake_run_mgr.fail_run.assert_called_once()
    fake_race_mgr.fail_run.assert_called_once_with("test-race", "run-1", result.error)
    fake_metrics_store.record_run.assert_awaited_once()
    assert fake_metrics_store.record_run.call_args.args[3] == "failed"


@pytest.mark.asyncio
async def test_run_step_async_without_race_id_skips_race_manager_updates(monkeypatch):
    fake_run_mgr = _fake_run_manager()
    fake_race_mgr = _fake_race_manager()
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)
    monkeypatch.setattr(pipeline_runner, "race_manager", fake_race_mgr)

    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(pipeline_runner, "get_handler", MagicMock(return_value=fake_handler))
    monkeypatch.setattr(pipeline_runner, "new_artifact_id", MagicMock(return_value="artifact-1"))
    monkeypatch.setattr(pipeline_runner, "save_artifact", MagicMock(return_value="path"))

    request = RunRequest(payload={})  # no race_id
    result = await pipeline_runner.run_step_async("agent", request)

    assert result.ok is True
    fake_race_mgr.complete_run.assert_not_called()
    fake_race_mgr.fail_run.assert_not_called()


@pytest.mark.asyncio
async def test_run_step_async_tolerates_artifact_save_failure(monkeypatch):
    fake_run_mgr = _fake_run_manager()
    fake_race_mgr = _fake_race_manager()
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)
    monkeypatch.setattr(pipeline_runner, "race_manager", fake_race_mgr)

    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(pipeline_runner, "get_handler", MagicMock(return_value=fake_handler))
    monkeypatch.setattr(pipeline_runner, "new_artifact_id", MagicMock(return_value="artifact-1"))
    monkeypatch.setattr(pipeline_runner, "save_artifact", MagicMock(side_effect=RuntimeError("disk full")))

    request = RunRequest(payload={"race_id": "test-race"})
    result = await pipeline_runner.run_step_async("agent", request)

    # The run still completes successfully; only the artifact ID is dropped.
    assert result.ok is True
    assert result.artifact_id is None


@pytest.mark.asyncio
async def test_run_step_async_race_manager_completion_failure_is_swallowed(monkeypatch):
    fake_run_mgr = _fake_run_manager()
    fake_race_mgr = _fake_race_manager()
    fake_race_mgr.complete_run = MagicMock(side_effect=RuntimeError("firestore unavailable"))
    monkeypatch.setattr(pipeline_runner, "logging_manager", _fake_logging_manager())
    monkeypatch.setattr(pipeline_runner, "run_manager", fake_run_mgr)
    monkeypatch.setattr(pipeline_runner, "race_manager", fake_race_mgr)

    fake_handler = MagicMock()
    fake_handler.handle = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(pipeline_runner, "get_handler", MagicMock(return_value=fake_handler))
    monkeypatch.setattr(pipeline_runner, "new_artifact_id", MagicMock(return_value="artifact-1"))
    monkeypatch.setattr(pipeline_runner, "save_artifact", MagicMock(return_value="path"))

    request = RunRequest(payload={"race_id": "test-race"})
    result = await pipeline_runner.run_step_async("agent", request)

    # Run itself still reports success even though the race record update failed.
    assert result.ok is True


def test_merge_options_applies_defaults_when_none():
    assert pipeline_runner._merge_options(None) == {"save_artifact": True}


def test_merge_options_overrides_defaults_with_explicit_values():
    from shared.pipeline_options import PipelineRunOptions

    opts = PipelineRunOptions(save_artifact=False, cheap_mode=True)
    merged = pipeline_runner._merge_options(opts)

    assert merged["save_artifact"] is False
    assert merged["cheap_mode"] is True


def test_safe_broadcast_swallows_errors_when_no_main_loop(monkeypatch):
    fake_manager = MagicMock()
    fake_manager._main_loop = None
    monkeypatch.setattr(pipeline_runner, "logging_manager", fake_manager)

    # Must not raise even with no running loop configured.
    pipeline_runner._safe_broadcast({"type": "run_started"})


def test_run_step_sync_wrapper_runs_event_loop(monkeypatch):
    async def fake_run_step_async(step, request, run_id=None):
        from pipeline_client.backend.models import RunResponse

        return RunResponse(step=step, ok=True, output={"done": True})

    monkeypatch.setattr(pipeline_runner, "run_step_async", fake_run_step_async)

    request = RunRequest(payload={"race_id": "test-race"})
    result = pipeline_runner.run_step("agent", request)

    assert result.ok is True
    assert result.output == {"done": True}
