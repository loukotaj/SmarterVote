# step_registry.py

from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable

from .handlers.v2_agent import V2AgentHandler
from .settings import settings
from .storage_backend import GCPStorageBackend, LocalStorageBackend, StorageBackend


def _init_storage_backend() -> StorageBackend:
    if settings.storage_mode == "gcp":
        if not settings.gcs_bucket:
            raise ValueError("gcs_bucket must be configured for gcp storage mode")
        return GCPStorageBackend(
            bucket=settings.gcs_bucket,
            firestore_project=settings.firestore_project,
        )
    published_dir = Path(__file__).resolve().parents[2] / "data/published"
    return LocalStorageBackend(settings.artifacts_dir, races_dir=published_dir)


@runtime_checkable
class StepHandler(Protocol):
    async def handle(self, payload: Dict[str, Any], options: Dict[str, Any]) -> Any: ...


_STORAGE_BACKEND = _init_storage_backend()


REGISTRY: Dict[str, StepHandler] = {
    "v2_agent": V2AgentHandler(_STORAGE_BACKEND),
}


def get_handler(step: str) -> StepHandler:
    try:
        return REGISTRY[step]
    except KeyError:
        raise KeyError(
            f"PipelineClient: Unknown step '{step}'. "
            f"Registered steps: {list(REGISTRY.keys())}. "
            f"Check your request and step_registry.py."
        )
