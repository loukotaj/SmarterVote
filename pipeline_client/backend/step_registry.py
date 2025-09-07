# step_registry.py

import logging
from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable

from .handlers.step01_discovery import Step01DiscoveryHandler
from .handlers.step01_extract import Step01ExtractHandler
from .handlers.step01_fetch import Step01FetchHandler

# Handlers that match your uploaded files
from .handlers.step01_metadata import Step01MetadataHandler  # requires storage backend
from .handlers.step01_relevance import Step01RelevanceHandler  # noqa: F401
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
    "step01a_metadata": Step01MetadataHandler(_STORAGE_BACKEND),
    "step01b_discovery": Step01DiscoveryHandler(),
    "step01c_fetch": Step01FetchHandler(),
    "step01d_extract": Step01ExtractHandler(),
    "step01e_relevance": Step01RelevanceHandler(_STORAGE_BACKEND),
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
