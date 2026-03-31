"""
Run management service for tracking pipeline executions.
"""

import json
import logging
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import RunInfo, RunOptions, RunRequest, RunStatus, RunStep


class RunManager:
    """Manages pipeline run lifecycle and state."""

    def __init__(self, storage_dir: str = "pipeline_client/runs"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_runs: Dict[str, RunInfo] = {}
        self._load_runs()
        self._log_handlers: Dict[str, Any] = {}

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
        """Attach a logging handler to capture logs for this run."""
        if run_id in self._log_handlers:
            return  # Already attached
        handler = self.RunLogHandler(self, run_id)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
        logger.addHandler(handler)
        self._log_handlers[run_id] = (handler, logger)

    def detach_run_logger(self, run_id: str):
        """Detach the logging handler for this run."""
        if run_id in self._log_handlers:
            handler, logger = self._log_handlers.pop(run_id)
            logger.removeHandler(handler)

    def _load_runs(self):
        """Load existing runs from storage."""
        try:
            for run_file in self.storage_dir.glob("*.json"):
                try:
                    with open(run_file, "r") as f:
                        data = json.load(f)
                        run_info = RunInfo(**data)
                        if run_info.status in [RunStatus.PENDING, RunStatus.RUNNING]:
                            # Mark incomplete runs as failed on startup
                            run_info.status = RunStatus.FAILED
                            run_info.error = "Process interrupted"
                            self._save_run(run_info)
                except Exception:
                    logging.exception("Failed to load run file %s, skipping", run_file)
                    # Don't load completed runs into active_runs to save memory
        except (OSError, json.JSONDecodeError, ValueError):
            logging.exception("Failed to load existing runs from storage")

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
            self._save_run(self.active_runs[run_id])
            self.attach_run_logger(run_id)

    def complete_run(self, run_id: str, artifact_id: Optional[str] = None, duration_ms: Optional[int] = None):
        """Mark a run as completed."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.COMPLETED
            run_info.completed_at = datetime.now(timezone.utc)
            run_info.artifact_id = artifact_id
            run_info.duration_ms = duration_ms
            self._save_run(run_info)
            self._upload_run_to_gcs_background(run_info)
            # Remove from active runs
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)

    def fail_run(self, run_id: str, error: str, duration_ms: Optional[int] = None):
        """Mark a run as failed."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.FAILED
            run_info.completed_at = datetime.now(timezone.utc)
            run_info.error = error
            run_info.duration_ms = duration_ms
            self._save_run(run_info)
            self._upload_run_to_gcs_background(run_info)
            # Remove from active runs
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)

    def cancel_run(self, run_id: str):
        """Cancel a running process."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.CANCELLED
            run_info.completed_at = datetime.now(timezone.utc)
            self._save_run(run_info)
            self._upload_run_to_gcs_background(run_info)
            # Remove from active runs
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)

    def get_run(self, run_id: str) -> Optional[RunInfo]:
        """Get run information."""
        # Check active runs first
        if run_id in self.active_runs:
            return self.active_runs[run_id]

        # Check storage
        run_file = self.storage_dir / f"{run_id}.json"
        if run_file.exists():
            try:
                with open(run_file, "r") as f:
                    data = json.load(f)
                    return RunInfo(**data)
            except Exception:
                pass

        return None

    def list_active_runs(self) -> List[RunInfo]:
        """List all active runs."""
        return list(self.active_runs.values())

    def list_recent_runs(self, limit: int = 50) -> List[RunInfo]:
        """List recent runs from storage."""
        runs = []

        # Add active runs
        runs.extend(self.active_runs.values())

        # Add completed runs from storage
        try:
            run_files = sorted(self.storage_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

            for run_file in run_files[:limit]:
                try:
                    with open(run_file, "r") as f:
                        data = json.load(f)
                        run_info = RunInfo(**data)
                        if run_info.run_id not in self.active_runs:
                            runs.append(run_info)
                except (OSError, json.JSONDecodeError, ValueError):
                    logging.exception("Failed to read run file %s", run_file)
                    continue
        except OSError:
            logging.exception("Failed to list recent runs from storage")

        # Sort by start time, most recent first (normalize tz-awareness for comparison)
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
        """Add a log entry to a run (in-memory only; disk flush happens on status changes)."""
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
        """Save run information to storage."""
        try:
            run_file = self.storage_dir / f"{run_info.run_id}.json"
            # Use dict to include logs
            data = run_info.model_dump(mode="json")
            if hasattr(run_info, "logs"):
                data["logs"] = run_info.logs
            with open(run_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError:
            # Do NOT use logging.exception here — it would re-enter the RunLogHandler
            # and cause infinite recursion. Write directly to stderr instead.
            print(f"Failed to save run {run_info.run_id}: {traceback.format_exc()}", file=sys.stderr)

    def _upload_run_to_gcs_background(self, run_info: RunInfo) -> None:
        """Fire-and-forget GCS upload in a daemon thread."""
        import threading
        threading.Thread(
            target=self._upload_run_to_gcs,
            args=(run_info,),
            daemon=True,
            name=f"gcs-upload-run-{run_info.run_id[:8]}",
        ).start()

    def _upload_run_to_gcs(self, run_info: RunInfo) -> None:
        """Upload run metadata to GCS so history survives container restarts.

        Logs are stripped to keep the payload small — the full log history lives
        in the local filesystem copy, which is already written before this runs.
        """
        try:
            from .settings import settings
            if not settings.gcs_bucket:
                return
            from google.cloud import storage  # type: ignore
            client = storage.Client()
            bucket = client.bucket(settings.gcs_bucket)
            blob = bucket.blob(f"runs/{run_info.run_id}.json")
            data = run_info.model_dump(mode="json")
            data.pop("logs", None)  # logs can be very large; kept local only
            blob.upload_from_string(json.dumps(data, indent=2, default=str), content_type="application/json")
        except ImportError:
            pass  # google-cloud-storage not installed
        except Exception:
            print(f"GCS upload failed for run {run_info.run_id}: {traceback.format_exc()}", file=sys.stderr)

    def sync_from_gcs(self) -> int:
        """Download run records from GCS into local storage (best-effort).

        Called on startup in cloud environments so that run history from previous
        container instances is visible in the admin UI. Returns number of runs synced.
        """
        try:
            from .settings import settings
            if not settings.gcs_bucket:
                return 0
            from google.cloud import storage  # type: ignore
            client = storage.Client()
            bucket = client.bucket(settings.gcs_bucket)
            count = 0
            for blob in bucket.list_blobs(prefix="runs/"):
                if not blob.name.endswith(".json"):
                    continue
                run_id = blob.name[len("runs/"):-len(".json")]
                local_file = self.storage_dir / f"{run_id}.json"
                if local_file.exists():
                    continue  # Already have a local copy
                try:
                    local_file.write_text(blob.download_as_text(), encoding="utf-8")
                    count += 1
                except Exception:
                    print(f"Failed to sync run {run_id} from GCS: {traceback.format_exc()}", file=sys.stderr)
            return count
        except ImportError:
            return 0
        except Exception:
            print(f"Failed to sync runs from GCS: {traceback.format_exc()}", file=sys.stderr)
            return 0


# Global run manager instance
run_manager = RunManager()
