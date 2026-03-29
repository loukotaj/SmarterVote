from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from .settings import settings
from .storage_backend import GCPStorageBackend, LocalStorageBackend, StorageBackend


def new_artifact_id(step: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{step}-{uuid.uuid4().hex[:8]}"


def _get_backend() -> StorageBackend:
    if settings.storage_mode == "gcp":
        if not settings.gcs_bucket:
            raise ValueError("gcs_bucket must be configured for gcp storage mode")
        return GCPStorageBackend(
            bucket=settings.gcs_bucket,
            firestore_project=settings.firestore_project,
        )
    return LocalStorageBackend(settings.artifacts_dir)


_backend = _get_backend()


def save_artifact(artifact_id: str, data: Dict[str, Any]) -> str:
    return _backend.save_artifact(artifact_id, data)


def load_artifact(artifact_id: str) -> Dict[str, Any]:
    return _backend.load_artifact(artifact_id)


def list_artifacts() -> Dict[str, Any]:
    return _backend.list_artifacts()


def save_race_json(race_id: str, data: Dict[str, Any]) -> str:
    return _backend.save_race_json(race_id, data)


def save_web_content(
    race_id: str,
    filename: str,
    content: bytes | str,
    content_type: str | None = None,
) -> str:
    return _backend.save_web_content(race_id, filename, content, content_type)
