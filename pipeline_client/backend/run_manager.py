"""
Run management service for tracking pipeline executions.

Storage strategy:
- Active (pending/running) runs are kept in-memory only — Cloud Run is single-instance,
  so this is safe and fast for hot-path updates.
- Completed/failed/cancelled runs are persisted to Firestore (collection: "pipeline_runs")
  in a background thread so the hot path is never blocked.
- Local dev (no FIRESTORE_PROJECT env var): completed runs live in an in-memory dict and
  are lost on restart — acceptable for local experimentation.

Firestore is the single source of truth; there is no local-file sync and no GCS run storage.
"""

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import RunInfo, RunOptions, RunRequest, RunStatus, RunStep

_COLLECTION = "pipeline_runs"


class RunManager:
    """Manages pipeline run lifecycle and state."""

    def __init__(self):
        self.active_runs: Dict[str, RunInfo] = {}
        self._log_handlers: Dict[str, Any] = {}
        # Completed-run store: Firestore client in production, in-memory dict in local dev
        self._db: Optional[Any] = None  # google.cloud.firestore.Client when available
        self._local_history: Dict[str, RunInfo] = {}  # local dev fallback
        self._init_store()

    def _init_store(self) -> None:
        """Connect to Firestore if FIRESTORE_PROJECT is set, else use in-memory fallback.

        On Cloud Run: FIRESTORE_PROJECT is required. Fail fast if missing.
        """
        project = os.getenv("FIRESTORE_PROJECT")
        is_cloud_run = bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_SERVICE"))

        if not project:
            if is_cloud_run:
                raise RuntimeError(
                    "Cloud Run detected but FIRESTORE_PROJECT is not set. "
                    "Run history requires Firestore for durability. "
                    "Set FIRESTORE_PROJECT via Terraform/deployment scripts."
                )
            logging.getLogger(__name__).info("RunManager: FIRESTORE_PROJECT not set — using in-memory run history (local dev mode)")
            return
        try:
            from google.cloud import firestore  # type: ignore
            self._db = firestore.Client(project=project)
            logging.getLogger(__name__).info("RunManager: using Firestore project=%s collection=%s", project, _COLLECTION)
        except ImportError:
            if is_cloud_run:
                raise RuntimeError("Cloud Run detected but google-cloud-firestore not installed.")
            logging.getLogger(__name__).warning("google-cloud-firestore not installed; using in-memory run history")
        except Exception as e:
            if is_cloud_run:
                raise RuntimeError(f"Cloud Run detected but failed to initialize Firestore: {e}")
            logging.getLogger(__name__).exception("Firestore init failed; using in-memory run history")

    class RunLogHandler(logging.Handler):
        def __init__(self, run_manager, run_id):
            super().__init__()
            self.run_manager = run_manager
            self.run_id = run_id
            self._emitting = False  # re-entrancy guard

        def emit(self, record):
            # Guard against recursive calls (e.g. _save_run failing and logging the error)
            if self._emitting:
                return
            self._emitting = True
            try:
                log_entry = {
                    "level": record.levelname.lower(),
                    "message": record.getMessage(),
                    "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                    "logger": record.name,
                    "filename": record.filename,
                    "funcName": record.funcName,
                    "lineno": record.lineno,
                }
                self.run_manager.add_run_log(self.run_id, log_entry)
            finally:
                self._emitting = False

    def attach_run_logger(self, run_id: str, logger_name: Optional[str] = None):
        """Attach a logging handler to capture logs for this run.

        Scoped to the 'pipeline' logger by default (not root) to avoid
        cross-run log bleed when multiple runs overlap.
        """
        if run_id in self._log_handlers:
            return  # Already attached
        handler = self.RunLogHandler(self, run_id)
        handler.setLevel(logging.DEBUG)
        target = logger_name or "pipeline"
        logger = logging.getLogger(target)
        logger.addHandler(handler)
        self._log_handlers[run_id] = (handler, logger)

    def detach_run_logger(self, run_id: str):
        """Detach the logging handler for this run."""
        if run_id in self._log_handlers:
            handler, logger = self._log_handlers.pop(run_id)
            logger.removeHandler(handler)

    def _load_runs(self):
        pass  # No-op: replaced by Firestore-primary storage (no startup sync needed)

    def create_run(self, steps: List[str], request: RunRequest) -> RunInfo:
        """Create a new pipeline run."""
        run_id = str(uuid.uuid4())

        # Merge options
        options = {}
        if request.options:
            options = request.options.model_dump(exclude_unset=True)

        run_info = RunInfo(
            run_id=run_id,
            status=RunStatus.PENDING,
            payload=request.payload,
            options=options,
            started_at=datetime.now(timezone.utc),
            steps=[RunStep(name=s) for s in steps],
        )

        self.active_runs[run_id] = run_info
        # Attach logs list to run_info
        run_info.logs = []
        self._save_run(run_info)
        return run_info

    def add_step(self, run_id: str, step: str) -> Optional[RunStep]:
        """Append a new step to an existing run."""
        run_info = self.active_runs.get(run_id)
        if not run_info:
            return None
        step_info = RunStep(name=step)
        run_info.steps.append(step_info)
        self._save_run(run_info)
        return step_info

    def update_step_status(
        self,
        run_id: str,
        step: str,
        status: RunStatus,
        artifact_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """Update status information for a specific step."""
        run_info = self.active_runs.get(run_id)
        if not run_info:
            return
        for step_info in run_info.steps:
            if step_info.name == step:
                step_info.status = status
                if status == RunStatus.RUNNING:
                    step_info.started_at = datetime.now(timezone.utc)
                if status in [RunStatus.COMPLETED, RunStatus.FAILED]:
                    step_info.completed_at = datetime.now(timezone.utc)
                    step_info.duration_ms = duration_ms
                    step_info.artifact_id = artifact_id
                    step_info.error = error
                    if artifact_id:
                        run_info.artifact_id = artifact_id
                break
        self._save_run(run_info)

    def start_run(self, run_id: str):
        """Mark a run as started."""
        if run_id in self.active_runs:
            self.active_runs[run_id].status = RunStatus.RUNNING
            self.attach_run_logger(run_id)
            self._save_run(self.active_runs[run_id])

    def complete_run(self, run_id: str, artifact_id: Optional[str] = None, duration_ms: Optional[int] = None) -> Optional["RunInfo"]:
        """Mark a run as completed. Returns the final RunInfo (or None if not found)."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.COMPLETED
            run_info.completed_at = datetime.now(timezone.utc)
            run_info.artifact_id = artifact_id
            run_info.duration_ms = duration_ms
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)
            self._persist_background(run_info)
            return run_info
        return None

    def fail_run(self, run_id: str, error: str, duration_ms: Optional[int] = None) -> Optional["RunInfo"]:
        """Mark a run as failed. Returns the final RunInfo (or None if not found)."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.FAILED
            run_info.completed_at = datetime.now(timezone.utc)
            run_info.error = error
            run_info.duration_ms = duration_ms
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)
            self._persist_background(run_info)
            return run_info
        return None

    def cancel_run(self, run_id: str) -> Optional["RunInfo"]:
        """Cancel a running process. Returns the final RunInfo (or None if not found)."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.CANCELLED
            run_info.completed_at = datetime.now(timezone.utc)
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)
            self._persist_background(run_info)
            return run_info
        return None

    def delete_run(self, run_id: str) -> bool:
        """Delete a completed/failed/cancelled run from history. Returns True if deleted."""
        if run_id in self.active_runs:
            return False  # Cannot delete an active run; cancel it first
        if self._db is not None:
            try:
                doc_ref = self._db.collection(_COLLECTION).document(run_id)
                if not doc_ref.get().exists:
                    return False
                doc_ref.delete()
                return True
            except Exception:
                logging.getLogger(__name__).exception("Firestore delete failed for run %s", run_id)
                return False
        else:
            if run_id in self._local_history:
                del self._local_history[run_id]
                return True
            return False

    def get_run(self, run_id: str) -> Optional[RunInfo]:
        """Get run information."""
        if run_id in self.active_runs:
            return self.active_runs[run_id]
        if self._db is not None:
            try:
                doc = self._db.collection(_COLLECTION).document(run_id).get()
                if doc.exists:
                    data = doc.to_dict() or {}
                    return RunInfo(**data)
            except Exception:
                logging.getLogger(__name__).exception("Firestore get failed for run %s", run_id)
        else:
            return self._local_history.get(run_id)
        return None

    def list_active_runs(self) -> List[RunInfo]:
        """List all active runs."""
        return list(self.active_runs.values())

    def list_recent_runs(self, limit: int = 50) -> List[RunInfo]:
        """List recent runs (active in memory + history from Firestore)."""
        runs: List[RunInfo] = list(self.active_runs.values())
        active_ids = set(self.active_runs.keys())

        if self._db is not None:
            try:
                from google.cloud.firestore import Query  # type: ignore
                docs = (
                    self._db.collection(_COLLECTION)
                    .order_by("started_at", direction=Query.DESCENDING)
                    .limit(limit)
                    .stream()
                )
                for doc in docs:
                    data = doc.to_dict() or {}
                    if data.get("run_id") not in active_ids:
                        try:
                            runs.append(RunInfo(**data))
                        except Exception:
                            pass
            except Exception:
                logging.getLogger(__name__).exception("Firestore list_recent_runs query failed")
        else:
            for run_id, run_info in self._local_history.items():
                if run_id not in active_ids:
                    runs.append(run_info)

        def _sort_key(r):
            dt = r.started_at
            if dt is None:
                return datetime.min.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        runs.sort(key=_sort_key, reverse=True)
        return runs[:limit]

    def add_run_log(self, run_id: str, log: dict):
        """Add a log entry to a run (in-memory only for active runs)."""
        run_info = self.active_runs.get(run_id)
        if run_info:
            if not hasattr(run_info, "logs") or run_info.logs is None:
                run_info.logs = []
            run_info.logs.append(log)

    def get_run_logs(self, run_id: str):
        run_info = self.get_run(run_id)
        if run_info and hasattr(run_info, "logs"):
            return run_info.logs
        return []

    def _save_run(self, run_info: RunInfo):
        """Persist active run state to Firestore so step progress survives page refreshes."""
        if self._db is not None:
            threading.Thread(
                target=self._write_firestore,
                args=(run_info,),
                daemon=True,
                name=f"fs-save-run-{run_info.run_id[:8]}",
            ).start()

    def _persist_background(self, run_info: RunInfo) -> None:
        """Fire-and-forget: persist a completed/failed/cancelled run to Firestore (or local dict)."""
        if self._db is not None:
            threading.Thread(
                target=self._write_firestore,
                args=(run_info,),
                daemon=True,
                name=f"fs-write-run-{run_info.run_id[:8]}",
            ).start()
        else:
            # Local dev: store in-memory (ephemeral)
            self._local_history[run_info.run_id] = run_info

    def _write_firestore(self, run_info: RunInfo) -> None:
        """Write run metadata to Firestore. Logs are excluded (in-memory only, can be large)."""
        if self._db is None:
            return
        try:
            data = run_info.model_dump(mode="json")
            data.pop("logs", None)  # logs are ephemeral; not stored in Firestore
            self._db.collection(_COLLECTION).document(run_info.run_id).set(data)
        except Exception:
            logging.getLogger(__name__).exception("Firestore write failed for run %s", run_info.run_id)

    # sync_from_gcs is intentionally removed: Firestore is now the source of truth.


# Global run manager instance
run_manager = RunManager()
