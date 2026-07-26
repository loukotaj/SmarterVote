"""Behavioral tests for pipeline_client.backend.storage's backend-selection and
thin delegation wrappers."""

from unittest.mock import MagicMock

import pytest

import pipeline_client.backend.storage as storage_module
from pipeline_client.backend.storage_backend import GCPStorageBackend, LocalStorageBackend


def test_get_backend_local_mode_returns_local_storage_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_module.settings, "storage_mode", "local")
    monkeypatch.setattr(storage_module.settings, "artifacts_dir", tmp_path / "artifacts")

    backend = storage_module._get_backend()

    assert isinstance(backend, LocalStorageBackend)


def test_get_backend_gcp_mode_without_bucket_raises_value_error(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "storage_mode", "gcp")
    monkeypatch.setattr(storage_module.settings, "gcs_bucket", None)

    with pytest.raises(ValueError, match="gcs_bucket must be configured"):
        storage_module._get_backend()


def test_get_backend_gcp_mode_with_bucket_constructs_gcp_backend(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "storage_mode", "gcp")
    monkeypatch.setattr(storage_module.settings, "gcs_bucket", "my-bucket")
    monkeypatch.setattr(storage_module.settings, "firestore_project", "my-project")

    fake_backend = MagicMock(spec=GCPStorageBackend)
    monkeypatch.setattr(storage_module, "GCPStorageBackend", MagicMock(return_value=fake_backend))

    backend = storage_module._get_backend()

    assert backend is fake_backend
    storage_module.GCPStorageBackend.assert_called_once_with(bucket="my-bucket", firestore_project="my-project")


def test_new_artifact_id_embeds_step_and_timestamp():
    artifact_id = storage_module.new_artifact_id("issues")

    assert "-issues-" in artifact_id
    prefix, step, suffix = artifact_id.split("-issues-")[0], "issues", artifact_id.split("-issues-")[1]
    assert len(prefix) == 16  # YYYYMMDDTHHMMSSZ
    assert len(suffix) == 8  # uuid4 hex[:8]


def test_new_artifact_id_is_unique_across_calls():
    assert storage_module.new_artifact_id("issues") != storage_module.new_artifact_id("issues")


def test_module_level_wrappers_delegate_to_backend_instance(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.save_artifact.return_value = "path/artifact"
    fake_backend.load_artifact.return_value = {"a": 1}
    fake_backend.list_artifacts.return_value = {"count": 0, "items": []}
    fake_backend.save_race_json.return_value = "path/race"
    fake_backend.save_web_content.return_value = "path/web"
    monkeypatch.setattr(storage_module, "_backend", fake_backend)

    assert storage_module.save_artifact("id", {"a": 1}) == "path/artifact"
    fake_backend.save_artifact.assert_called_once_with("id", {"a": 1})

    assert storage_module.load_artifact("id") == {"a": 1}
    fake_backend.load_artifact.assert_called_once_with("id")

    assert storage_module.list_artifacts() == {"count": 0, "items": []}
    fake_backend.list_artifacts.assert_called_once_with()

    assert storage_module.save_race_json("race-1", {"id": "race-1"}) == "path/race"
    fake_backend.save_race_json.assert_called_once_with("race-1", {"id": "race-1"})

    assert storage_module.save_web_content("race-1", "f.html", "<html/>", "text/html") == "path/web"
    fake_backend.save_web_content.assert_called_once_with("race-1", "f.html", "<html/>", "text/html")
