"""Behavioral tests for pipeline_client.backend.step_registry."""

from unittest.mock import MagicMock

import pytest

import pipeline_client.backend.step_registry as step_registry
from pipeline_client.backend.handlers.agent import AgentHandler
from pipeline_client.backend.storage_backend import GCPStorageBackend, LocalStorageBackend


def test_get_handler_returns_registered_agent_handler():
    handler = step_registry.get_handler("agent")

    assert isinstance(handler, AgentHandler)
    assert hasattr(handler, "handle")


def test_get_handler_unknown_step_raises_descriptive_key_error():
    with pytest.raises(KeyError) as exc_info:
        step_registry.get_handler("not-a-real-step")

    message = str(exc_info.value)
    assert "not-a-real-step" in message
    assert "agent" in message


def test_init_storage_backend_local_mode_uses_published_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(step_registry.settings, "storage_mode", "local")
    monkeypatch.setattr(step_registry.settings, "artifacts_dir", tmp_path / "artifacts")

    backend = step_registry._init_storage_backend()

    assert isinstance(backend, LocalStorageBackend)
    assert backend.races_dir.name == "published"


def test_init_storage_backend_gcp_mode_without_bucket_raises(monkeypatch):
    monkeypatch.setattr(step_registry.settings, "storage_mode", "gcp")
    monkeypatch.setattr(step_registry.settings, "gcs_bucket", None)

    with pytest.raises(ValueError, match="gcs_bucket must be configured"):
        step_registry._init_storage_backend()


def test_init_storage_backend_gcp_mode_with_bucket_constructs_gcp_backend(monkeypatch):
    monkeypatch.setattr(step_registry.settings, "storage_mode", "gcp")
    monkeypatch.setattr(step_registry.settings, "gcs_bucket", "my-bucket")
    monkeypatch.setattr(step_registry.settings, "firestore_project", "my-project")
    fake_backend = MagicMock(spec=GCPStorageBackend)
    monkeypatch.setattr(step_registry, "GCPStorageBackend", MagicMock(return_value=fake_backend))

    backend = step_registry._init_storage_backend()

    assert backend is fake_backend
    step_registry.GCPStorageBackend.assert_called_once_with(bucket="my-bucket", firestore_project="my-project")
