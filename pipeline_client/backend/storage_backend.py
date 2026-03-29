from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for storage backends."""

    def save_artifact(self, artifact_id: str, data: Dict[str, Any]) -> str: ...

    def load_artifact(self, artifact_id: str) -> Dict[str, Any]: ...

    def list_artifacts(self) -> Dict[str, Any]: ...

    def save_race_json(self, race_id: str, data: Dict[str, Any]) -> str: ...

    def save_web_content(
        self,
        race_id: str,
        filename: str,
        content: bytes | str,
        content_type: str | None = None,
        kind: str = "raw",
    ) -> str: ...


class LocalStorageBackend:
    """Local filesystem storage implementation."""

    def __init__(self, artifacts_dir: Path, races_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.races_dir = races_dir or self.artifacts_dir / "races"
        self.races_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = self.artifacts_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir = self.artifacts_dir / "extracted"
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        self.relevant_dir = self.artifacts_dir / "relevant"
        self.relevant_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_path(self, artifact_id: str) -> Path:
        return self.artifacts_dir / f"{artifact_id}.json"

    def save_artifact(self, artifact_id: str, data: Dict[str, Any]) -> str:
        path = self._artifact_path(artifact_id)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(path)

    def load_artifact(self, artifact_id: str) -> Dict[str, Any]:
        path = self._artifact_path(artifact_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_artifacts(self) -> Dict[str, Any]:
        files = sorted(self.artifacts_dir.glob("*.json"))
        return {
            "count": len(files),
            "items": [
                {
                    "id": f.stem,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                }
                for f in files
            ],
        }

    def save_race_json(self, race_id: str, data: Dict[str, Any]) -> str:
        path = self.races_dir / f"{race_id}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(path)

    def save_web_content(
        self,
        race_id: str,
        filename: str,
        content: bytes | str,
        content_type: str | None = None,
        kind: str = "raw",
    ) -> str:
        base_dir = {
            "raw": self.raw_dir,
            "extracted": self.extracted_dir,
            "relevant": self.relevant_dir,
        }.get(kind, self.raw_dir)

        race_dir = base_dir / race_id
        race_dir.mkdir(parents=True, exist_ok=True)
        path = race_dir / filename
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return str(path)


class GCPStorageBackend:
    """GCP storage using GCS for all data (artifacts, race JSON, and web content)."""

    def __init__(self, bucket: str, firestore_project: str | None = None) -> None:
        try:
            from google.cloud import storage
        except Exception as e:  # pragma: no cover - import guard
            raise RuntimeError("google-cloud-storage is required for GCP storage") from e

        self._storage_client = storage.Client()
        self.bucket = self._storage_client.bucket(bucket)

    def save_artifact(self, artifact_id: str, data: Dict[str, Any]) -> str:
        blob = self.bucket.blob(f"artifacts/{artifact_id}.json")
        blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
        return f"gs://{self.bucket.name}/artifacts/{artifact_id}.json"

    def load_artifact(self, artifact_id: str) -> Dict[str, Any]:
        blob = self.bucket.blob(f"artifacts/{artifact_id}.json")
        if not blob.exists():
            raise FileNotFoundError(artifact_id)
        return json.loads(blob.download_as_text())

    def list_artifacts(self) -> Dict[str, Any]:
        blobs = list(self._storage_client.list_blobs(self.bucket.name, prefix="artifacts/"))
        items = [
            {
                "id": b.name.removeprefix("artifacts/").removesuffix(".json"),
                "path": f"gs://{self.bucket.name}/{b.name}",
                "size": b.size,
                "modified": b.updated.timestamp() if b.updated else None,
            }
            for b in blobs
            if b.name.endswith(".json")
        ]
        return {"count": len(items), "items": items}

    def save_race_json(self, race_id: str, data: Dict[str, Any]) -> str:
        blob = self.bucket.blob(f"races/{race_id}.json")
        blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
        return f"gs://{self.bucket.name}/races/{race_id}.json"

    def save_web_content(
        self,
        race_id: str,
        filename: str,
        content: bytes | str,
        content_type: str | None = None,
        kind: str = "raw",
    ) -> str:
        blob = self.bucket.blob(f"{race_id}/{kind}/{filename}")
        if isinstance(content, bytes):
            blob.upload_from_string(content, content_type=content_type or "application/octet-stream")
        else:
            blob.upload_from_string(content, content_type=content_type or "text/plain")
        return f"gs://{self.bucket.name}/{race_id}/{kind}/{filename}"
