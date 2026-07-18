"""Shared storage names and repository-root-relative local paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

GCS_DRAFTS_PREFIX = "drafts"
GCS_RACES_PREFIX = "races"
GCS_RETIRED_PREFIX = "retired"
GCS_ARTIFACTS_PREFIX = "artifacts"
GCS_CHECKPOINTS_PREFIX = "checkpoints"

FIRESTORE_QUEUE_COLLECTION = "pipeline_queue"
FIRESTORE_RUNS_COLLECTION = "pipeline_runs"
FIRESTORE_RACES_COLLECTION = "races"
FIRESTORE_SEARCH_CACHE_COLLECTION = "search_cache"
FIRESTORE_PAGE_CACHE_COLLECTION = "page_cache"


@dataclass(frozen=True)
class LocalPaths:
    repo_root: Path
    data_dir: Path
    drafts_dir: Path
    published_dir: Path
    retired_dir: Path
    artifacts_dir: Path
    cache_dir: Path
    metrics_db_path: Path

    @classmethod
    def resolve(cls, repo_root: str | Path | None = None) -> "LocalPaths":
        configured_root = repo_root or os.getenv("SMARTERVOTE_REPO_ROOT")
        root = Path(configured_root).expanduser().resolve() if configured_root else Path(__file__).resolve().parents[1]
        data = root / "data"
        return cls(
            repo_root=root,
            data_dir=data,
            drafts_dir=data / GCS_DRAFTS_PREFIX,
            published_dir=data / "published",
            retired_dir=data / GCS_RETIRED_PREFIX,
            artifacts_dir=root / "pipeline_client" / "artifacts",
            cache_dir=data / "cache",
            metrics_db_path=data / "pipeline_metrics.db",
        )


local_paths = LocalPaths.resolve()
