import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from .settings import settings


def new_artifact_id(step: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{step}-{uuid.uuid4().hex[:8]}"


def artifact_path(artifact_id: str) -> Path:
    return settings.artifacts_dir / f"{artifact_id}.json"


def save_artifact(artifact_id: str, data: Dict[str, Any]) -> Path:
    path = artifact_path(artifact_id)
    path.write_text(json.dumps(data, indent=2))
    return path


def load_artifact(artifact_id: str) -> Dict[str, Any]:
    path = artifact_path(artifact_id)
    return json.loads(path.read_text())


def list_artifacts() -> Dict[str, Any]:
    files = sorted(settings.artifacts_dir.glob("*.json"))
    return {
        "count": len(files),
        "items": [{"id": f.stem, "path": str(f), "size": f.stat().st_size, "modified": f.stat().st_mtime} for f in files],
    }
