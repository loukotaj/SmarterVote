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
    ) -> str: ...


class LocalStorageBackend:
    """Local filesystem storage implementation."""

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.races_dir = self.artifacts_dir / "races"
        self.races_dir.mkdir(parents=True, exist_ok=True)
        self.web_dir = self.artifacts_dir / "web"
        self.web_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_path(self, artifact_id: str) -> Path:
        return self.artifacts_dir / f"{artifact_id}.json"

    def save_artifact(self, artifact_id: str, data: Dict[str, Any]) -> str:
        path = self._artifact_path(artifact_id)
        path.write_text(json.dumps(data, indent=2))
        return str(path)

    def load_artifact(self, artifact_id: str) -> Dict[str, Any]:
        path = self._artifact_path(artifact_id)
        return json.loads(path.read_text())

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
        path.write_text(json.dumps(data, indent=2))
        return str(path)

    def save_web_content(
        self,
        race_id: str,
        filename: str,
        content: bytes | str,
        content_type: str | None = None,
    ) -> str:
        race_dir = self.web_dir / race_id
        race_dir.mkdir(parents=True, exist_ok=True)
        path = race_dir / filename
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return str(path)


class GCPStorageBackend:
    """GCP storage using Firestore and GCS."""

    def __init__(self, bucket: str, firestore_project: str | None = None) -> None:
        try:
            from google.cloud import firestore, storage
        except Exception as e:  # pragma: no cover - import guard
            raise RuntimeError("google-cloud libraries are required for GCP storage") from e

        self.firestore_client = firestore.Client(project=firestore_project)
        self.bucket = storage.Client().bucket(bucket)

    def save_artifact(self, artifact_id: str, data: Dict[str, Any]) -> str:
        doc = self.firestore_client.collection("artifacts").document(artifact_id)
        doc.set(data)
        return f"firestore://{self.firestore_client.project}/artifacts/{artifact_id}"

    def load_artifact(self, artifact_id: str) -> Dict[str, Any]:
        doc = self.firestore_client.collection("artifacts").document(artifact_id).get()
        if not doc.exists:
            raise FileNotFoundError(artifact_id)
        return doc.to_dict() or {}

    def list_artifacts(self) -> Dict[str, Any]:  # pragma: no cover - simple wrapper
        docs = list(self.firestore_client.collection("artifacts").stream())
        items = [{"id": d.id} for d in docs]
        return {"count": len(items), "items": items}

    def save_race_json(self, race_id: str, data: Dict[str, Any]) -> str:
        doc = self.firestore_client.collection("races").document(race_id)
        doc.set(data)
        return f"firestore://{self.firestore_client.project}/races/{race_id}"

    def save_web_content(
        self,
        race_id: str,
        filename: str,
        content: bytes | str,
        content_type: str | None = None,
    ) -> str:
        blob = self.bucket.blob(f"{race_id}/{filename}")
        if isinstance(content, bytes):
            blob.upload_from_string(content, content_type=content_type or "application/octet-stream")
        else:
            blob.upload_from_string(content, content_type=content_type or "text/plain")
        return f"gs://{self.bucket.name}/{race_id}/{filename}"
