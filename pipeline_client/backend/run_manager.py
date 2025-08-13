"""
Run management service for tracking pipeline executions.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional
from .models import RunInfo, RunStatus, RunRequest, RunOptions
import json
from pathlib import Path
import logging


class RunManager:
    """Manages pipeline run lifecycle and state."""

    def __init__(self, storage_dir: str = "pipeline_client/runs"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_runs: Dict[str, RunInfo] = {}
        self._load_runs()
        self._log_handlers: Dict[str, logging.Handler] = {}
    class RunLogHandler(logging.Handler):
        def __init__(self, run_manager, run_id):
            super().__init__()
            self.run_manager = run_manager
            self.run_id = run_id

        def emit(self, record):
            log_entry = {
                "level": record.levelname,
                "message": record.getMessage(),
                "time": datetime.fromtimestamp(record.created).isoformat(),
                "logger": record.name,
                "filename": record.filename,
                "funcName": record.funcName,
                "lineno": record.lineno,
            }
            self.run_manager.add_run_log(self.run_id, log_entry)

    def attach_run_logger(self, run_id: str, logger_name: str = None):
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
                with open(run_file, "r") as f:
                    data = json.load(f)
                    run_info = RunInfo(**data)
                    if run_info.status in [RunStatus.PENDING, RunStatus.RUNNING]:
                        # Mark incomplete runs as failed on startup
                        run_info.status = RunStatus.FAILED
                        run_info.error = "Process interrupted"
                        self._save_run(run_info)
                    # Don't load completed runs into active_runs to save memory
        except Exception:
            pass  # Continue if loading fails

    def create_run(self, step: str, request: RunRequest) -> RunInfo:
        """Create a new pipeline run."""
        run_id = str(uuid.uuid4())

        # Merge options
        options = {}
        if request.options:
            options = request.options.model_dump(exclude_unset=True)

        run_info = RunInfo(
            run_id=run_id,
            step=step,
            status=RunStatus.PENDING,
            payload=request.payload,
            options=options,
            started_at=datetime.now(),
        )

        self.active_runs[run_id] = run_info
        # Attach logs list to run_info
        run_info.logs = []
        self._save_run(run_info)
        return run_info

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
            run_info.completed_at = datetime.now()
            run_info.artifact_id = artifact_id
            run_info.duration_ms = duration_ms
            self._save_run(run_info)
            # Remove from active runs
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)

    def fail_run(self, run_id: str, error: str, duration_ms: Optional[int] = None):
        """Mark a run as failed."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.FAILED
            run_info.completed_at = datetime.now()
            run_info.error = error
            run_info.duration_ms = duration_ms
            self._save_run(run_info)
            # Remove from active runs
            del self.active_runs[run_id]
            self.detach_run_logger(run_id)

    def cancel_run(self, run_id: str):
        """Cancel a running process."""
        if run_id in self.active_runs:
            run_info = self.active_runs[run_id]
            run_info.status = RunStatus.CANCELLED
            run_info.completed_at = datetime.now()
            self._save_run(run_info)
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
                except Exception:
                    continue
        except Exception:
            pass

        # Sort by start time, most recent first
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    def add_run_log(self, run_id: str, log: dict):
        """Add a log entry to a run and persist it."""
        # Try active first
        run_info = self.active_runs.get(run_id)
        if not run_info:
            # Try loading from disk
            run_info = self.get_run(run_id)
        if run_info:
            if not hasattr(run_info, 'logs') or run_info.logs is None:
                run_info.logs = []
            run_info.logs.append(log)
            self._save_run(run_info)

    def get_run_logs(self, run_id: str):
        run_info = self.get_run(run_id)
        if run_info and hasattr(run_info, 'logs'):
            return run_info.logs
        return []

    def _save_run(self, run_info: RunInfo):
        """Save run information to storage."""
        try:
            run_file = self.storage_dir / f"{run_info.run_id}.json"
            # Use dict to include logs
            data = run_info.model_dump(mode="json")
            if hasattr(run_info, 'logs'):
                data['logs'] = run_info.logs
            with open(run_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            pass  # Continue if saving fails


# Global run manager instance
run_manager = RunManager()
