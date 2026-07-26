"""Queue-item processor for the long-lived local worker.

The heavy lifting (agent execution, checkpointing, draft save) is delegated to
``AgentHandler``. The processor runs
each race with a far-future deadline, so a *deadline-driven* handoff never
fires. ``AgentHandler`` can still raise ``HandoffTriggered`` for a reason
unrelated to the deadline — its per-unit issue-research retry bookkeeping
(``continue_incomplete_work``) is unconditional — so ``process_claimed_item``
follows any such handoff in-process (reloading the continuation's own options
and checkpoint, then looping) instead of treating it as fatal. That keeps a
race running start-to-finish in one process with no *externally* visible
GCS-checkpoint reload/re-dispatch (the source of the CF cost/latency overhead),
while still never discarding completed work if a handoff does fire. This
module owns the Firestore claim and terminal-state bookkeeping so Cloud Run Job
and local Docker executions show up identically in admin.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from shared.pipeline_config import RetentionConfig
from shared.race_catalog import build_race_summary_fields, build_versioned_catalog_fields
from shared.run_health import RunFailureReason, RunHealthStatus, classify_exception

logger = logging.getLogger("pipeline_worker")

# 24h default: long enough that a deadline check alone would never trigger handoff.
# It does NOT stop AgentHandler's per-unit retry bookkeeping (continue_incomplete_work
# is unconditional there) from raising HandoffTriggered when a research unit doesn't
# complete in one pass — see the in-process continuation loop in process_claimed_item.
WORKER_DEADLINE_SECONDS = max(3600, int(os.getenv("WORKER_DEADLINE_SECONDS", str(24 * 3600))))
_LEASE_SECONDS = max(60, int(os.getenv("WORKER_LEASE_SECONDS", "300")))
_LEASE_RENEW_SECONDS = max(15, min(int(os.getenv("WORKER_LEASE_RENEW_SECONDS", "60")), _LEASE_SECONDS // 2))
_MAX_LOCAL_HANDOFFS = max(1, int(os.getenv("WORKER_MAX_HANDOFFS", "50")))
_RETENTION = RetentionConfig.from_env()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _queue_ttl_at(now: Optional[datetime] = None) -> datetime:
    return (now or _now()) + timedelta(days=_RETENTION.completed_queue_days)


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


def _set_race_if_current(db: Any, race_id: str, run_id: str, update: Dict[str, Any]) -> bool:
    """Update the race record only if this run still owns it (guards ghost writes)."""
    race_ref = db.collection("races").document(race_id)
    try:
        race_doc = race_ref.get()
        race_data = race_doc.to_dict() if getattr(race_doc, "exists", False) else {}
        if not isinstance(race_data, dict):
            race_data = {}
    except Exception as exc:
        logger.warning("Could not read race %s before terminal update for run %s: %s", race_id, run_id, exc)
        return False
    if race_data.get("current_run_id") != run_id:
        logger.info(
            "Skipping race update for %s from run %s (current_run_id=%s)", race_id, run_id, race_data.get("current_run_id")
        )
        return False
    update = dict(update)
    update.setdefault("race_id", race_id)
    race_ref.set(update, merge=True)
    return True


def _load_gcs_json(gcs: Any, bucket_name: str, path: str) -> Optional[Dict[str, Any]]:
    if gcs is None:
        return None
    try:
        if path.startswith("gs://"):
            without_scheme = path[5:]
            bucket_name, _, obj_key = without_scheme.partition("/")
        else:
            obj_key = path
        blob = gcs.bucket(bucket_name).blob(obj_key)
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


def claim_item(db: Any, item_ref: Any, lease_owner: str, expected_runner: str) -> Optional[Dict[str, Any]]:
    """Atomically claim an item for the expected runner (pending → running).

    Returns the item data on success, or ``None`` when the item is missing,
    routed elsewhere, already terminal, or under another worker's live lease.
    """
    from google.cloud import firestore as _fs  # type: ignore
    from google.cloud.firestore_v1 import Increment  # type: ignore

    @_fs.transactional
    def _claim(transaction, ref):
        doc = ref.get(transaction=transaction)
        if not getattr(doc, "exists", False):
            return None
        data = doc.to_dict() or {}
        if data.get("runner") != expected_runner:
            return None
        now = _now()
        status = data.get("status")
        if status != "pending" and not (status == "running" and _lease_expired(data, now)):
            return None
        update = {
            "status": "running",
            "lease_owner": lease_owner,
            "lease_expires_at": now + timedelta(seconds=_LEASE_SECONDS),
            "lease_renewed_at": now.isoformat(),
            "lease_attempts": Increment(1),
        }
        update["started_at" if status == "pending" else "recovered_at"] = now.isoformat()
        transaction.update(ref, update)
        return data

    try:
        return _claim(db.transaction(), item_ref)
    except Exception as exc:
        logger.warning("Claim failed for local queue item %s: %s", getattr(item_ref, "id", "?"), exc)
        return None


def claim_local_item(db: Any, item_ref: Any, lease_owner: str) -> Optional[Dict[str, Any]]:
    """Backward-compatible local-runner claim helper."""
    return claim_item(db, item_ref, lease_owner, "local")


def _start_lease_heartbeat(db: Any, item_ref: Any, lease_owner: str):
    stop_event = threading.Event()

    def _heartbeat() -> None:
        from google.cloud import firestore as fs_module  # type: ignore
        from google.cloud.firestore_v1 import Increment  # type: ignore

        while not stop_event.wait(_LEASE_RENEW_SECONDS):
            now = _now()

            @fs_module.transactional
            def _renew(transaction, ref):
                doc = ref.get(transaction=transaction)
                data = doc.to_dict() if getattr(doc, "exists", False) else {}
                if data.get("status") != "running" or data.get("lease_owner") != lease_owner:
                    return False
                transaction.update(
                    ref,
                    {
                        "lease_expires_at": now + timedelta(seconds=_LEASE_SECONDS),
                        "lease_renewed_at": now.isoformat(),
                        "lease_renewals": Increment(1),
                    },
                )
                return True

            try:
                if not _renew(db.transaction(), item_ref):
                    logger.warning("Lease lost for queue item %s", getattr(item_ref, "id", "?"))
                    return
            except Exception:
                logger.exception("Failed to renew queue lease")

    thread = threading.Thread(target=_heartbeat, name="worker-lease-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


async def _run_agent(
    race_id: str, run_id: str, options: Dict[str, Any], existing_data: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Invoke AgentHandler.handle() (same entry the CF uses).

    Returns the handler's result dict (which carries ``run_health``) so the
    caller can persist the run's machine-readable health verdict alongside
    its terminal ``status`` — the two are independent signals.
    """
    from pipeline_client.backend.handlers.agent import AgentHandler

    payload: Dict[str, Any] = {"race_id": race_id}
    if existing_data:
        payload["existing_data"] = existing_data
    return await AgentHandler().handle(payload, options)


async def process_claimed_item(
    db: Any,
    gcs: Any,
    bucket_name: str,
    item_id: str,
    item_data: Dict[str, Any],
    lease_owner: str,
    runner: str = "local",
) -> None:
    """Run a claimed queue item end-to-end and finalize Firestore state.

    A far-future deadline avoids deadline-driven dispatch; research retry
    continuations are followed in-process below.
    """
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Increment  # type: ignore

    from pipeline_client.backend.handlers.agent import AgentCancelled, HandoffTriggered

    race_id = item_data.get("race_id", "")
    options: Dict[str, Any] = dict(item_data.get("options") or {})
    run_id = item_data.get("run_id") or uuid.uuid4().hex
    is_continuation = bool(item_data.get("is_continuation"))
    existing_data_gcs_path = item_data.get("existing_data_gcs_path")
    item_ref = db.collection("pipeline_queue").document(item_id)

    if not race_id:
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
                "runner": runner,
            }
        )
    else:
        run_ref.update({"status": "running", "queue_item_id": item_id})

    db.collection("races").document(race_id).set(
        {"status": "running", "current_run_id": run_id, "race_id": race_id}, merge=True
    )

    existing_data: Optional[Dict[str, Any]] = None
    if is_continuation and existing_data_gcs_path:
        existing_data = _load_gcs_json(gcs, bucket_name, existing_data_gcs_path)

    options["run_id"] = run_id
    options["queue_item_id"] = item_id
    import time as _time

    lease_stop, lease_thread = _start_lease_heartbeat(db, item_ref, lease_owner)
    success = False
    error_msg = ""
    handoffs_followed = 0
    last_result: Optional[Dict[str, Any]] = None
    failure_reason: Optional[RunFailureReason] = None
    try:
        while True:
            # Re-applied every pass: a fresh far-future deadline so deadline-driven
            # handoff never fires. A handoff can still fire for per-unit retry
            # bookkeeping (AgentHandler's continue_incomplete_work is unconditional,
            # independent of deadline_at) — that's followed in-process below instead
            # of being treated as fatal, since giving up here discards all completed
            # research for the run.
            options["deadline_at"] = _time.time() + WORKER_DEADLINE_SECONDS
            try:
                last_result = await _run_agent(race_id, run_id, options, existing_data)
                success = True
                break
            except HandoffTriggered as exc:
                handoffs_followed += 1
                if handoffs_followed > _MAX_LOCAL_HANDOFFS:
                    error_msg = (
                        f"Gave up after {handoffs_followed} in-process continuations for run {run_id} "
                        f"(remaining steps: {exc.remaining_steps})"
                    )
                    failure_reason = RunFailureReason.BUDGET_EXHAUSTED
                    logger.warning(error_msg)
                    break
                cont_ref = db.collection("pipeline_queue").document(exc.continuation_item_id)
                cont_doc = cont_ref.get()
                cont_data = cont_doc.to_dict() if getattr(cont_doc, "exists", False) else None
                if not isinstance(cont_data, dict):
                    error_msg = f"Continuation item {exc.continuation_item_id} missing for run {run_id}"
                    failure_reason = RunFailureReason.UNKNOWN_ERROR
                    logger.warning(error_msg)
                    break
                logger.info(
                    "Local worker following continuation %s in-process (pass %d) for run %s: remaining=%s",
                    exc.continuation_item_id,
                    handoffs_followed,
                    run_id,
                    exc.remaining_steps,
                )
                options = dict(cont_data.get("options") or {})
                options["run_id"] = run_id
                options["queue_item_id"] = item_id
                cont_existing_path = cont_data.get("existing_data_gcs_path")
                existing_data = _load_gcs_json(gcs, bucket_name, cont_existing_path) if cont_existing_path else None
                try:
                    cont_ref.delete()
                except Exception:
                    logger.debug("Could not delete followed continuation item %s", exc.continuation_item_id, exc_info=True)
    except AgentCancelled as exc:
        logger.info("Local run %s cancelled: %s", run_id, exc)
        item_ref.update(
            {
                "status": "cancelled",
                "completed_at": _now().isoformat(),
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
        run_ref.update(
            {
                "status": "cancelled",
                "completed_at": SERVER_TIMESTAMP,
                "run_health": {
                    "status": RunHealthStatus.FAILED.value,
                    "reasons": [RunFailureReason.CANCELLED.value],
                    "step_failures": [],
                    "summary": str(exc) or None,
                },
            }
        )
        _set_race_if_current(db, race_id, run_id, {"status": "cancelled", "current_run_id": None})
        return
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        failure_reason = classify_exception(exc)
        logger.exception("Local run %s failed: %s", run_id, exc)
    finally:
        lease_stop.set()
        lease_thread.join(timeout=2)

    if success:
        # run_health is the definitive "did this actually succeed" verdict —
        # independent of `status`. A run can be marked completed here while
        # run_health.status is "failed"/"degraded" (e.g. review didn't pass,
        # or a step like finance silently produced no data for anyone).
        run_health = last_result.get("run_health") if isinstance(last_result, dict) else None
        item_ref.update(
            {
                "status": "completed",
                "completed_at": _now().isoformat(),
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
        run_update: Dict[str, Any] = {"status": "completed", "progress": 100, "completed_at": SERVER_TIMESTAMP}
        if run_health is not None:
            run_update["run_health"] = run_health
        run_ref.update(run_update)
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
        draft_data = _load_gcs_json(gcs, bucket_name, f"drafts/{race_id}.json")
        if isinstance(draft_data, dict):
            db.collection("races").document(race_id).set(_draft_catalog_update(race_id, draft_data), merge=True)
    else:
        reason = failure_reason or RunFailureReason.UNKNOWN_ERROR
        run_health = {
            "status": RunHealthStatus.FAILED.value,
            "reasons": [reason.value],
            "step_failures": [],
            "summary": error_msg or None,
        }
        item_ref.update(
            {
                "status": "failed",
                "error": error_msg or "Unknown error",
                "lease_owner": None,
                "lease_expires_at": None,
                "ttl_at": _queue_ttl_at(),
            }
        )
        run_ref.update(
            {
                "status": "failed",
                "error": error_msg or "Unknown error",
                "completed_at": SERVER_TIMESTAMP,
                "run_health": run_health,
            }
        )
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
