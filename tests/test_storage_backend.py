"""Behavioral tests for pipeline_client.backend.storage_backend."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipeline_client.backend.storage_backend import GCPStorageBackend, LocalStorageBackend


class TestLocalStorageBackend:
    def test_init_creates_expected_directory_tree(self, tmp_path):
        LocalStorageBackend(tmp_path / "artifacts")

        assert (tmp_path / "artifacts").is_dir()
        assert (tmp_path / "artifacts" / "races").is_dir()
        assert (tmp_path / "artifacts" / "raw").is_dir()
        assert (tmp_path / "artifacts" / "extracted").is_dir()
        assert (tmp_path / "artifacts" / "relevant").is_dir()

    def test_init_accepts_explicit_races_dir(self, tmp_path):
        races_dir = tmp_path / "published"
        backend = LocalStorageBackend(tmp_path / "artifacts", races_dir=races_dir)

        assert backend.races_dir == races_dir
        assert races_dir.is_dir()

    def test_save_and_load_artifact_round_trips(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        path = backend.save_artifact("my-artifact", {"a": 1, "b": [1, 2]})

        assert path.endswith("my-artifact.json")
        loaded = backend.load_artifact("my-artifact")
        assert loaded == {"a": 1, "b": [1, 2]}

    def test_load_missing_artifact_raises_file_not_found(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        with pytest.raises(FileNotFoundError):
            backend.load_artifact("does-not-exist")

    def test_list_artifacts_reports_count_and_metadata(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")
        backend.save_artifact("one", {"x": 1})
        backend.save_artifact("two", {"x": 2})

        result = backend.list_artifacts()

        assert result["count"] == 2
        ids = {item["id"] for item in result["items"]}
        assert ids == {"one", "two"}
        for item in result["items"]:
            assert "size" in item and item["size"] > 0
            assert "modified" in item

    def test_list_artifacts_empty_directory(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        result = backend.list_artifacts()

        assert result == {"count": 0, "items": []}

    def test_save_race_json_writes_under_races_dir(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        path = backend.save_race_json("ga-senate-2026", {"id": "ga-senate-2026"})

        written = json.loads((tmp_path / "artifacts" / "races" / "ga-senate-2026.json").read_text())
        assert written == {"id": "ga-senate-2026"}
        assert path.endswith("ga-senate-2026.json")

    def test_save_web_content_text_default_kind_is_raw(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        path = backend.save_web_content("race-1", "page.html", "<html></html>")

        assert (tmp_path / "artifacts" / "raw" / "race-1" / "page.html").read_text() == "<html></html>"
        assert "raw" in path

    def test_save_web_content_bytes_writes_binary(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        backend.save_web_content("race-1", "image.png", b"\x89PNG\r\n", kind="extracted")

        written = (tmp_path / "artifacts" / "extracted" / "race-1" / "image.png").read_bytes()
        assert written == b"\x89PNG\r\n"

    def test_save_web_content_unknown_kind_falls_back_to_raw_dir(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        backend.save_web_content("race-1", "note.txt", "hi", kind="not-a-real-kind")

        assert (tmp_path / "artifacts" / "raw" / "race-1" / "note.txt").read_text() == "hi"

    def test_save_web_content_relevant_kind_uses_relevant_dir(self, tmp_path):
        backend = LocalStorageBackend(tmp_path / "artifacts")

        backend.save_web_content("race-1", "note.txt", "hi", kind="relevant")

        assert (tmp_path / "artifacts" / "relevant" / "race-1" / "note.txt").read_text() == "hi"


class TestGCPStorageBackend:
    def _make_backend(self, monkeypatch):
        fake_client = MagicMock()
        fake_bucket = MagicMock()
        fake_bucket.name = "my-bucket"
        fake_client.bucket.return_value = fake_bucket
        fake_storage_module = SimpleNamespace(Client=lambda: fake_client)
        monkeypatch.setitem(__import__("sys").modules, "google.cloud.storage", fake_storage_module)
        backend = GCPStorageBackend(bucket="my-bucket")
        return backend, fake_client, fake_bucket

    def test_save_artifact_uploads_json_and_returns_gs_uri(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        bucket.blob.return_value = blob

        result = backend.save_artifact("abc", {"x": 1})

        bucket.blob.assert_called_with("artifacts/abc.json")
        blob.upload_from_string.assert_called_once()
        assert result == "gs://my-bucket/artifacts/abc.json"

    def test_load_artifact_missing_blob_raises_file_not_found(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        blob.exists.return_value = False
        bucket.blob.return_value = blob

        with pytest.raises(FileNotFoundError):
            backend.load_artifact("missing")

    def test_load_artifact_existing_blob_returns_parsed_json(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_text.return_value = json.dumps({"a": 1})
        bucket.blob.return_value = blob

        assert backend.load_artifact("present") == {"a": 1}

    def test_list_artifacts_filters_to_json_blobs(self, monkeypatch):
        backend, client, bucket = self._make_backend(monkeypatch)
        json_blob = SimpleNamespace(name="artifacts/one.json", size=10, updated=None)
        other_blob = SimpleNamespace(name="artifacts/one.json.tmp", size=5, updated=None)
        client.list_blobs.return_value = [json_blob, other_blob]

        result = backend.list_artifacts()

        assert result["count"] == 1
        assert result["items"][0]["id"] == "one"
        assert result["items"][0]["path"] == "gs://my-bucket/artifacts/one.json"

    def test_save_race_json_uses_races_prefix(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        bucket.blob.return_value = blob

        result = backend.save_race_json("ga-senate-2026", {"id": "ga-senate-2026"})

        bucket.blob.assert_called_with("races/ga-senate-2026.json")
        assert result == "gs://my-bucket/races/ga-senate-2026.json"

    def test_save_web_content_text_defaults_to_text_plain(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        bucket.blob.return_value = blob

        backend.save_web_content("race-1", "page.html", "<html></html>")

        bucket.blob.assert_called_with("race-1/raw/page.html")
        blob.upload_from_string.assert_called_with("<html></html>", content_type="text/plain")

    def test_save_web_content_bytes_defaults_to_octet_stream(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        bucket.blob.return_value = blob

        backend.save_web_content("race-1", "image.bin", b"\x00\x01", kind="extracted")

        blob.upload_from_string.assert_called_with(b"\x00\x01", content_type="application/octet-stream")

    def test_save_web_content_respects_explicit_content_type(self, monkeypatch):
        backend, _client, bucket = self._make_backend(monkeypatch)
        blob = MagicMock()
        bucket.blob.return_value = blob

        backend.save_web_content("race-1", "data.json", "{}", content_type="application/json")

        blob.upload_from_string.assert_called_with("{}", content_type="application/json")

    def test_init_raises_runtime_error_when_google_cloud_storage_missing(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "google.cloud" or name.startswith("google.cloud."):
                raise ImportError("no google-cloud-storage installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(RuntimeError, match="google-cloud-storage is required"):
            GCPStorageBackend(bucket="my-bucket")
