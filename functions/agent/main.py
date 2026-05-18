"""
Agent Cloud Function — triggered by new `pipeline_queue/{item_id}` documents.

Execution model:
  1. Eventarc Firestore trigger fires when a pipeline_queue document is created.
  2. CF reads the queue item, claims it (pending → running) atomically.
  3. Runs the agent via AgentHandler; FirestoreLogger streams live progress.
  4. HandoffTriggered: agent wrote a continuation queue item → CF exits cleanly.
  5. Any other exception: marks item + run as failed.

Idempotency: uses a Firestore transaction to transition pending→running,
so duplicate CF invocations on the same item are safe no-ops.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import functions_framework
from cloudevents.http import CloudEvent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agent_cf")

_FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
_GCS_BUCKET = os.getenv("GCS_BUCKET", "")

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_fs_db = None
_gcs_client = None


def _get_fs():
    global _fs_db
    if _fs_db is None:
        from google.cloud import firestore  # type: ignore

        _fs_db = firestore.Client(project=_FIRESTORE_PROJECT) if _FIRESTORE_PROJECT else firestore.Client()
    return _fs_db


def _get_gcs():
    global _gcs_client
    if _gcs_client is None:
        try:
            from google.cloud import storage  # type: ignore

            _gcs_client = storage.Client()
        except Exception as exc:
            logger.warning("GCS client init failed: %s", exc)
    return _gcs_client


def _set_race_if_current(db: Any, race_id: str, run_id: str, update: Dict[str, Any]) -> bool:
    """Update the race record only if this invocation still owns it."""
    race_ref = db.collection("races").document(race_id)
    try:
        race_doc = race_ref.get()
        race_data = race_doc.to_dict() if getattr(race_doc, "exists", False) else {}
        if not isinstance(race_data, dict):
            race_data = {}
    except Exception as exc:
        logger.warning("Could not read race %s before terminal update for run %s: %s", race_id, run_id, exc)
        return False

    current_run_id = race_data.get("current_run_id")
    if current_run_id != run_id:
        logger.info(
            "Skipping race update for %s from run %s because current_run_id is %s",
            race_id,
            run_id,
            current_run_id,
        )
        return False
    race_ref.set(update, merge=True)
    return True


# ---------------------------------------------------------------------------
# CF entry point (Firestore document.v1.created trigger)
# ---------------------------------------------------------------------------


@functions_framework.cloud_event
def process_queue_item(cloud_event: CloudEvent) -> None:
    """Handle a new pipeline_queue document creation event."""
    # Extract document path from event subject
    # Subject format: projects/{p}/databases/{d}/documents/pipeline_queue/{item_id}
    subject = cloud_event.get("subject", "") or ""
    parts = subject.split("/")
    if len(parts) < 2:
        logger.error("Could not parse document ID from subject: %s", subject)
        return
    item_id = parts[-1]

    logger.info("CF triggered for queue item: %s", item_id)

    db = _get_fs()

    # ---------------------------------------------------------------------------
    # Atomic claim: transition pending → running
    # ---------------------------------------------------------------------------
    item_ref = db.collection("pipeline_queue").document(item_id)

    from google.cloud import firestore as _fs_module  # type: ignore

    @_fs_module.transactional
    def _claim(transaction, item_ref):
        doc = item_ref.get(transaction=transaction)
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("status") != "pending":
            return None  # already running / cancelled / finished — skip
        transaction.update(
            item_ref,
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return data

    item_data: Optional[Dict[str, Any]] = _claim(db.transaction(), item_ref)

    if item_data is None:
        logger.info("Queue item %s already claimed or missing — skipping", item_id)
        return

    race_id: str = item_data.get("race_id", "")
    options: Dict[str, Any] = item_data.get("options") or {}
    run_id: str = item_data.get("run_id") or _gen_id()
    is_continuation: bool = bool(item_data.get("is_continuation"))
    existing_data_gcs_path: Optional[str] = item_data.get("existing_data_gcs_path")

    if not race_id:
        logger.error("Queue item %s missing race_id", item_id)
        item_ref.update({"status": "failed", "error": "Missing race_id"})
        return

    # ---------------------------------------------------------------------------
    # Initialise pipeline_runs document
    # ---------------------------------------------------------------------------
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Increment  # type: ignore

    run_ref = db.collection("pipeline_runs").document(run_id)
    if not run_ref.get().exists:
        run_ref.set(
            {
                "run_id": run_id,
                "race_id": race_id,
                "payload": {"race_id": race_id},
                "status": "running",
                "progress": 0,
                "current_step": None,
                "started_at": SERVER_TIMESTAMP,
                "queue_item_id": item_id,
                "is_continuation": is_continuation,
                "options": options,
            }
        )
    else:
        run_ref.update({"status": "running", "queue_item_id": item_id})

    # Update race record
    db.collection("races").document(race_id).set(
        {"status": "running", "current_run_id": run_id},
        merge=True,
    )

    # ---------------------------------------------------------------------------
    # Load existing data from GCS checkpoint (continuations only)
    # ---------------------------------------------------------------------------
    existing_data: Optional[Dict[str, Any]] = None
    if is_continuation and existing_data_gcs_path:
        existing_data = _load_gcs_json(existing_data_gcs_path)
        if existing_data:
            logger.info("Loaded checkpoint from %s for continuation run %s", existing_data_gcs_path, run_id)
        else:
            logger.warning("Could not load checkpoint %s — running fresh", existing_data_gcs_path)

    # Pass run_id and deadline into options for the handler
    options["run_id"] = run_id
    options["queue_item_id"] = item_id
    options["deadline_at"] = time.time() + int(os.getenv("AGENT_DEADLINE_SECONDS", "3300"))

    # ---------------------------------------------------------------------------
    # Execute agent
    # ---------------------------------------------------------------------------
    success = False
    error_msg = ""

    try:
        _run_agent(race_id, run_id, options, existing_data, item_id, is_continuation)
        success = True
    except _HandoffExit as exc:
        # Clean handoff to continuation — not a failure
        logger.info(
            "Handoff submitted for run %s, continuation item %s (%d steps remaining)",
            run_id,
            exc.continuation_item_id,
            len(exc.remaining_steps),
        )
        current_item = item_ref.get()
        current_item_data = current_item.to_dict() if getattr(current_item, "exists", False) else {}
        if (current_item_data or {}).get("status") == "cancelled":
            logger.info(
                "Queue item %s was cancelled during handoff; cancelling continuation %s", item_id, exc.continuation_item_id
            )
            run_ref.update({"status": "cancelled", "completed_at": SERVER_TIMESTAMP})
            try:
                db.collection("pipeline_queue").document(exc.continuation_item_id).update(
                    {
                        "status": "cancelled",
                        "cancelled_at": datetime.now(timezone.utc).isoformat(),
                        "cancel_reason": f"Parent queue item {item_id} was cancelled during handoff",
                    }
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to cancel continuation %s after parent cancellation: %s", exc.continuation_item_id, cleanup_exc
                )
            return
        item_ref.update({"status": "continued", "continuation_item_id": exc.continuation_item_id})
        continuation_run_id = getattr(exc, "continuation_run_id", None) or exc.continuation_item_id
        run_ref.update(
            {
                "status": "continued",
                "continuation_item_id": exc.continuation_item_id,
                "continuation_run_id": continuation_run_id,
            }
        )
        _set_race_if_current(
            db,
            race_id,
            run_id,
            {"status": "queued", "current_run_id": continuation_run_id},
        )
        return
    except _CancelledExit as exc:
        logger.info("Agent run %s cancelled: %s", run_id, exc)
        item_ref.update({"status": "cancelled", "completed_at": datetime.now(timezone.utc).isoformat()})
        run_ref.update({"status": "cancelled", "completed_at": SERVER_TIMESTAMP})
        _set_race_if_current(db, race_id, run_id, {"status": "cancelled", "current_run_id": None})
        return
    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Agent run %s failed: %s", run_id, exc)
    finally:
        if not success and not error_msg:
            # Shouldn't happen, but guard
            error_msg = "Unknown error"

    # ---------------------------------------------------------------------------
    # Finalise
    # ---------------------------------------------------------------------------
    if success:
        item_ref.update({"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()})
        run_ref.update(
            {
                "status": "completed",
                "progress": 100,
                "completed_at": SERVER_TIMESTAMP,
            }
        )
        _set_race_if_current(
            db,
            race_id,
            run_id,
            {
                "status": "draft",
                "current_run_id": None,
                "last_run_id": run_id,
                "last_run_at": SERVER_TIMESTAMP,
                "last_run_status": "completed",
                "total_runs": Increment(1),
            },
        )
    else:
        item_ref.update({"status": "failed", "error": error_msg})
        run_ref.update({"status": "failed", "error": error_msg, "completed_at": SERVER_TIMESTAMP})
        _set_race_if_current(
            db,
            race_id,
            run_id,
            {
                "status": "failed",
                "current_run_id": None,
                "last_run_id": run_id,
                "last_run_at": SERVER_TIMESTAMP,
                "last_run_status": "failed",
                "total_runs": Increment(1),
            },
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _HandoffExit(Exception):
    """Wraps HandoffTriggered so it can be caught separately from normal exceptions."""

    def __init__(self, continuation_item_id: str, remaining_steps: list, continuation_run_id: str | None = None):
        self.continuation_item_id = continuation_item_id
        self.remaining_steps = remaining_steps
        self.continuation_run_id = continuation_run_id


class _CancelledExit(Exception):
    """Wraps AgentCancelled from the handler."""


def _gen_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _load_gcs_json(path: str) -> Optional[Dict[str, Any]]:
    """Load a JSON file from GCS. Path can be a full gs:// URI or a bare object key."""
    if not _GCS_BUCKET and not path.startswith("gs://"):
        return None
    client = _get_gcs()
    if client is None:
        return None
    try:
        if path.startswith("gs://"):
            # gs://bucket/object/key
            without_scheme = path[5:]
            bucket_name, _, obj_key = without_scheme.partition("/")
        else:
            bucket_name = _GCS_BUCKET
            obj_key = path
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(obj_key)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
    except Exception as exc:
        logger.warning("Failed to load GCS JSON %s: %s", path, exc)
        return None


def _run_agent(
    race_id: str,
    run_id: str,
    options: Dict[str, Any],
    existing_data: Optional[Dict[str, Any]],
    item_id: str,
    is_continuation: bool,
) -> None:
    """
    Import and invoke AgentHandler.handle() synchronously.

    The handler is written as an async function; we run it in a new event loop
    since Cloud Functions Python runtime doesn't provide one by default.
    """
    import asyncio

    # Merge existing_data into payload so the agent can resume from checkpoint
    payload: Dict[str, Any] = {"race_id": race_id}
    if existing_data:
        payload["existing_data"] = existing_data

    # Import here to avoid module-level import failures if pipeline_client
    # packages aren't fully initialised at module import time
    try:
        from pipeline_client.backend.handlers.agent import AgentCancelled, AgentHandler, HandoffTriggered
    except ImportError as exc:
        raise RuntimeError(f"Failed to import AgentHandler: {exc}") from exc

    handler = AgentHandler()

    async def _run():
        return await handler.handle(payload, options)

    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        # Re-raise HandoffTriggered as _HandoffExit so caller can distinguish it
        from pipeline_client.backend.handlers.agent import AgentCancelled, HandoffTriggered

        if isinstance(exc, HandoffTriggered):
            raise _HandoffExit(
                exc.continuation_item_id,
                exc.remaining_steps,
                exc.continuation_run_id,
            ) from exc
        if isinstance(exc, AgentCancelled):
            raise _CancelledExit(str(exc)) from exc
        raise
