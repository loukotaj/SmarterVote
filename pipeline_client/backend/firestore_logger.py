"""Firestore-backed log writer for pipeline runs.

Writes structured log entries and run progress updates to Firestore so the
frontend can subscribe via onSnapshot instead of a WebSocket connection.

Collections written:
  pipeline_runs/{run_id}                  — progress/status fields
  pipeline_runs/{run_id}/logs/{log_id}    — individual log entries

All writes are fire-and-forget: exceptions are caught and logged to stderr so
a Firestore outage never crashes the agent.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pipeline_client.logging_utils import sanitize_log_data, sanitize_log_message

logger = logging.getLogger("pipeline")

_db = None  # lazy singleton


def _get_db():
    """Return a Firestore client, or None if unavailable."""
    global _db
    if _db is not None:
        return _db
    project = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
    try:
        from google.cloud import firestore  # type: ignore

        _db = firestore.Client(project=project) if project else firestore.Client()
        return _db
    except Exception as exc:
        logger.debug("FirestoreLogger: could not init Firestore client: %s", exc)
        return None


class FirestoreLogger:
    """Writes run logs and progress to Firestore.

    Usage::

        fl = FirestoreLogger(run_id)
        fl.log("info", "Discovery phase started", step="discovery")
        fl.update_progress(run_id, pct=25, current_step="discovery")
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._log_counter = 0

    # ------------------------------------------------------------------
    # Log entry writer
    # ------------------------------------------------------------------

    def log(
        self,
        level: str,
        message: str,
        *,
        step: Optional[str] = None,
        race_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write a single log entry to pipeline_runs/{run_id}/logs/{id}."""
        try:
            db = _get_db()
            if db is None:
                return
            self._log_counter += 1
            # Zero-padded counter ensures documents sort chronologically even
            # when Firestore timestamps have the same millisecond.
            ts = datetime.now(timezone.utc)
            doc_id = f"{int(ts.timestamp() * 1000):016d}_{self._log_counter:06d}"
            entry: Dict[str, Any] = {
                "timestamp": ts.isoformat(),
                "level": level,
                "message": sanitize_log_message(message),
                "run_id": self.run_id,
            }
            if step:
                entry["step"] = step
            if race_id:
                entry["race_id"] = race_id
            if extra:
                entry["extra"] = sanitize_log_data(extra)
            (db.collection("pipeline_runs").document(self.run_id).collection("logs").document(doc_id).set(entry))
        except Exception as exc:
            # Never crash the agent because of a logging failure
            logger.debug("FirestoreLogger.log failed: %s", exc)

    # ------------------------------------------------------------------
    # Progress / status update
    # ------------------------------------------------------------------

    def update_progress(
        self,
        pct: int,
        *,
        current_step: Optional[str] = None,
        current_step_progress: Optional[int] = None,
        progress_message: Optional[str] = None,
        remaining_steps: Optional[list] = None,
        status: Optional[str] = None,
    ) -> None:
        """Update the top-level run document with current progress fields."""
        db = _get_db()
        if db is None:
            return
        try:
            update: Dict[str, Any] = {
                "progress": pct,
                "progress_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if current_step is not None:
                update["current_step"] = current_step
            if current_step_progress is not None:
                update["current_step_progress"] = max(0, min(100, int(current_step_progress)))
            if progress_message is not None:
                update["progress_message"] = sanitize_log_message(progress_message)
            if remaining_steps is not None:
                update["remaining_steps"] = remaining_steps
            if status is not None:
                update["status"] = status
            db.collection("pipeline_runs").document(self.run_id).set(update, merge=True)
        except Exception as exc:
            logger.debug("FirestoreLogger.update_progress failed: %s", exc)

    def mark_completed(self, *, duration_ms: Optional[int] = None) -> None:
        """Mark the run document as completed."""
        db = _get_db()
        if db is None:
            return
        try:
            update: Dict[str, Any] = {
                "status": "completed",
                "progress": 100,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            if duration_ms is not None:
                update["duration_ms"] = duration_ms
            db.collection("pipeline_runs").document(self.run_id).set(update, merge=True)
        except Exception as exc:
            logger.debug("FirestoreLogger.mark_completed failed: %s", exc)

    def mark_failed(self, error: str, *, duration_ms: Optional[int] = None) -> None:
        """Mark the run document as failed."""
        db = _get_db()
        if db is None:
            return
        try:
            update: Dict[str, Any] = {
                "status": "failed",
                "error": sanitize_log_message(error),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            if duration_ms is not None:
                update["duration_ms"] = duration_ms
            db.collection("pipeline_runs").document(self.run_id).set(update, merge=True)
        except Exception as exc:
            logger.debug("FirestoreLogger.mark_failed failed: %s", exc)

    def mark_continued(self, continuation_run_id: str) -> None:
        """Mark run as continued (handed off to a new CF invocation)."""
        db = _get_db()
        if db is None:
            return
        try:
            db.collection("pipeline_runs").document(self.run_id).set(
                {
                    "status": "continued",
                    "continuation_run_id": continuation_run_id,
                    "continued_at": datetime.now(timezone.utc).isoformat(),
                },
                merge=True,
            )
        except Exception as exc:
            logger.debug("FirestoreLogger.mark_continued failed: %s", exc)
