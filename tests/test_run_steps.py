import asyncio
import importlib
import sys
import types

import pytest
from fastapi.testclient import TestClient

from pipeline_client.backend import run_manager as rm_module
from pipeline_client.backend import settings as settings_module
from pipeline_client.backend.models import RunRequest, RunStatus
from pipeline_client.backend.run_manager import RunManager


class DummyHandler:
    async def handle(self, payload, options):  # pragma: no cover - simple stub
        return payload


def test_run_records_multiple_steps(monkeypatch, tmp_path):
    """Running multiple steps under one run_id stores each step."""

    # Stub step registry before importing modules that depend on it
    dummy_registry = types.SimpleNamespace()
    dummy_registry.REGISTRY = {}
    dummy_registry.get_handler = lambda step: dummy_registry.REGISTRY[step]
    monkeypatch.setitem(sys.modules, "pipeline_client.backend.step_registry", dummy_registry)

    pipeline_runner = importlib.import_module("pipeline_client.backend.pipeline_runner")
    main_module = importlib.import_module("pipeline_client.backend.main")

    # Temporary run manager and artifacts directory
    tmp_runs = tmp_path / "runs"
    tmp_runs.mkdir()
    new_rm = RunManager(storage_dir=str(tmp_runs))
    rm_module.run_manager = new_rm
    pipeline_runner.run_manager = new_rm
    main_module.run_manager = new_rm

    tmp_artifacts = tmp_path / "artifacts"
    tmp_artifacts.mkdir()
    monkeypatch.setattr(settings_module.settings, "artifacts_dir", tmp_artifacts)

    # Register dummy steps
    dummy_registry.REGISTRY["dummy1"] = DummyHandler()
    dummy_registry.REGISTRY["dummy2"] = DummyHandler()

    # First step starts a new run
    resp1 = asyncio.run(pipeline_runner.run_step_async("dummy1", RunRequest(payload={})))
    run_id = resp1.meta["run_id"]

    # Second step continues the same run
    asyncio.run(pipeline_runner.run_step_async("dummy2", RunRequest(payload={}), run_id=run_id))

    run_info = new_rm.get_run(run_id)
    assert run_info is not None
    assert [s.name for s in run_info.steps] == ["dummy1", "dummy2"]
    assert all(step.status == RunStatus.COMPLETED for step in run_info.steps)

    client = TestClient(main_module.app)
    resp = client.get(f"/run/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) == 2

    resp = client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    found = next(r for r in runs if r["run_id"] == run_id)
    assert len(found["steps"]) == 2
