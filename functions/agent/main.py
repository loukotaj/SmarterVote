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
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import functions_framework
from cloudevents.http import CloudEvent

from shared.pipeline_config import RetentionConfig
from shared.race_catalog import build_race_summary_fields, build_versioned_catalog_fields

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agent_cf")

_FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT") or os.getenv("PROJECT_ID")
_GCS_BUCKET = os.getenv("GCS_BUCKET", "")
_QUEUE_LEASE_SECONDS = max(60, int(os.getenv("QUEUE_LEASE_SECONDS", "180")))
_QUEUE_LEASE_RENEW_SECONDS = max(15, min(int(os.getenv("QUEUE_LEASE_RENEW_SECONDS", "60")), _QUEUE_LEASE_SECONDS // 2))
_RETENTION = RetentionConfig.from_env()

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
    update = dict(update)
    update.setdefault("race_id", race_id)
    race_ref.set(update, merge=True)
    return True


def _as_utc_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _lease_expired(data: Dict[str, Any], now: datetime) -> bool:
    expires_at = _as_utc_datetime(data.get("lease_expires_at"))
    return expires_at is None or expires_at <= now


def _queue_item_owned(item_ref: Any, lease_owner: str) -> bool:
    try:
        doc = item_ref.get()
        data = doc.to_dict() if getattr(doc, "exists", False) else {}
        return data.get("status") == "running" and data.get("lease_owner") == lease_owner
    except Exception:
        logger.exception("Failed to verify queue lease ownership")
        return False


def _queue_ttl_at(now: Optional[datetime] = None) -> datetime:
    base = now or datetime.now(timezone.utc)
    return base + timedelta(days=_RETENTION.completed_queue_days)


def _start_lease_heartbeat(db: Any, item_ref: Any, lease_owner: str) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def _heartbeat() -> None:
        from google.cloud import firestore as fs_module  # type: ignore
        from google.cloud.firestore_v1 import Increment  # type: ignore

        while not stop_event.wait(_QUEUE_LEASE_RENEW_SECONDS):
            now = datetime.now(timezone.utc)

            @fs_module.transactional
            def _renew(transaction, ref):
                doc = ref.get(transaction=transaction)
                data = doc.to_dict() if getattr(doc, "exists", False) else {}
                if data.get("status") != "running" or data.get("lease_owner") != lease_owner:
                    return False
                transaction.update(
                    ref,
                    {
                        "lease_expires_at": now + timedelta(seconds=_QUEUE_LEASE_SECONDS),
                        "lease_renewed_at": now.isoformat(),
                        "lease_renewals": Increment(1),
                    },
                )
                return True

            try:
                if not _renew(db.transaction(), item_ref):
                    logger.warning("Lease ownership lost for queue item %s", getattr(item_ref, "id", "unknown"))
                    return
            except Exception:
                logger.exception("Failed to renew queue lease")

    thread = threading.Thread(target=_heartbeat, name="queue-lease-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


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
    lease_owner = f"{os.getenv('K_REVISION', 'local')}:{uuid.uuid4()}"

    from google.cloud import firestore as _fs_module  # type: ignore
    from google.cloud.firestore_v1 import Increment  # type: ignore

    @_fs_module.transactional
    def _claim(transaction, item_ref):
        doc = item_ref.get(transaction=transaction)
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        # Items tagged for the local Docker worker are left untouched here so the
        # Eventarc-triggered CF and the long-lived worker never fight over them.
        if data.get("runner") == "local":
            return {"_claim_skipped_status": "runner_local"}
        now = datetime.now(timezone.utc)
        status = data.get("status")
        if status != "pending" and not (status == "running" and _lease_expired(data, now)):
            return {"_claim_skipped_status": status}
        update = {
            "status": "running",
            "lease_owner": lease_owner,
            "lease_expires_at": now + timedelta(seconds=_QUEUE_LEASE_SECONDS),
            "lease_renewed_at": now.isoformat(),
            "lease_attempts": Increment(1),
        }
        if status == "pending":
            update["started_at"] = now.isoformat()
        else:
            update["recovered_at"] = now.isoformat()
        transaction.update(item_ref, update)
        return data

    item_data: Optional[Dict[str, Any]] = _claim(db.transaction(), item_ref)

    if item_data is None:
        logger.info("Queue item %s is missing — skipping", item_id)
        return
    skipped_status = item_data.get("_claim_skipped_status")
    if skipped_status == "runner_local":
        logger.info("Queue item %s is tagged runner=local — leaving for the local worker", item_id)
        return
    if skipped_status == "running":
        raise RuntimeError(f"Queue item {item_id} has an active lease; retry after lease expiry")
    if skipped_status:
        logger.info("Queue item %s is already %s — skipping", item_id, skipped_status)
        return

    race_id: str = item_data.get("race_id", "")
    options: Dict[str, Any] = item_data.get("options") or {}
    run_id: str = item_data.get("run_id") or _gen_id()
    is_continuation: bool = bool(item_data.get("is_continuation"))
    existing_data_gcs_path: Optional[str] = item_data.get("existing_data_gcs_path")

    if not race_id:
        logger.error("Queue item %s missing race_id", item_id)
        item_ref.update(
            {
                "status": "failed",
                "error": "Missing race_id",
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
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
        {"status": "running", "current_run_id": run_id, "race_id": race_id},
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
    lease_stop, lease_thread = _start_lease_heartbeat(db, item_ref, lease_owner)

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
                        "ttl_at": _queue_ttl_at(),
                    }
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to cancel continuation %s after parent cancellation: %s", exc.continuation_item_id, cleanup_exc
                )
            return
        if (current_item_data or {}).get("lease_owner") != lease_owner:
            logger.warning("Ignoring handoff from run %s after lease ownership was lost", run_id)
            return
        item_ref.update(
            {
                "status": "continued",
                "continuation_item_id": exc.continuation_item_id,
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
        continuation_run_id = getattr(exc, "continuation_run_id", None) or run_id
        run_ref.update(
            {
                "status": "running",
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
        current_item = item_ref.get()
        current_item_data = current_item.to_dict() if getattr(current_item, "exists", False) else {}
        if (current_item_data or {}).get("status") == "running" and (current_item_data or {}).get(
            "lease_owner"
        ) != lease_owner:
            logger.warning("Ignoring cancellation finalization for run %s after lease ownership was lost", run_id)
            return
        logger.info("Agent run %s cancelled: %s", run_id, exc)
        item_ref.update(
            {
                "status": "cancelled",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
        run_ref.update({"status": "cancelled", "completed_at": SERVER_TIMESTAMP})
        _set_race_if_current(db, race_id, run_id, {"status": "cancelled", "current_run_id": None})
        return
    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Agent run %s failed: %s", run_id, exc)
    finally:
        lease_stop.set()
        lease_thread.join(timeout=2)
        if not success and not error_msg:
            # Shouldn't happen, but guard
            error_msg = "Unknown error"

    # ---------------------------------------------------------------------------
    # Finalise
    # ---------------------------------------------------------------------------
    if not _queue_item_owned(item_ref, lease_owner):
        logger.warning("Skipping finalization for run %s after lease ownership was lost", run_id)
        return
    if success:
        item_ref.update(
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
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
        draft_data = _load_gcs_json(f"drafts/{race_id}.json")
        if isinstance(draft_data, dict):
            db.collection("races").document(race_id).set(_draft_catalog_update(race_id, draft_data), merge=True)
    else:
        item_ref.update(
            {
                "status": "failed",
                "error": error_msg,
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
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


def _draft_catalog_update(race_id: str, draft_data: Dict[str, Any]) -> Dict[str, Any]:
    fields = build_race_summary_fields(race_id, draft_data)
    fields.update(build_versioned_catalog_fields("draft", draft_data))
    fields["draft_updated_at"] = draft_data.get("updated_utc")
    return fields


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
