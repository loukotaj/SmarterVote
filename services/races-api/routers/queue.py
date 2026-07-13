"""Queue management endpoints.

All endpoints are Auth0-JWT protected via verify_token dependency.
Queue items are stored in Firestore `pipeline_queue` collection and picked up
by a one-shot Cloud Run Job or the explicitly selected local Docker worker.
"""

import logging
import os
import uuid
from typing import Any, Dict

import firestore_helpers
from auth import verify_token
from cloud_run_jobs import dispatch_pipeline_job
from fastapi import APIRouter, Depends, HTTPException
from request_models import RaceQueueRequest, validate_race_id
from routers.utils import _queue_ttl_at

from shared.pipeline_config import PIPELINE_STEP_LABELS, PIPELINE_STEP_ORDER, PIPELINE_STEP_WEIGHTS, RetentionConfig

router = APIRouter()
logger = logging.getLogger("races_api")

_PIPELINE_STEPS = list(PIPELINE_STEP_ORDER)
_PIPELINE_STEP_DETAILS = [
    {"id": step, "label": PIPELINE_STEP_LABELS[step], "weight": PIPELINE_STEP_WEIGHTS[step]} for step in PIPELINE_STEP_ORDER
]
_ACTIVE_STATUSES = {"pending", "running"}
_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "continued"}
_INACTIVE_RACE_STATUSES = {"draft", "published", "empty", "failed", "cancelled"}
_RETENTION = RetentionConfig.from_env()


def _default_runner() -> str:
    return os.getenv("PIPELINE_DEFAULT_RUNNER", "local").strip().lower()


def _dispatch_if_cloud_run(db: Any, item: Dict[str, Any]) -> Dict[str, Any] | None:
    if item.get("runner") != "cloud_run":
        return None
    try:
        dispatch = dispatch_pipeline_job(str(item["id"]))
        update = {"dispatch_status": "submitted", **dispatch}
        db.collection("pipeline_queue").document(str(item["id"])).update(update)
        return update
    except Exception as exc:
        error = f"Cloud Run Job dispatch failed: {exc}"
        db.collection("pipeline_queue").document(str(item["id"])).update(
            {"status": "failed", "dispatch_status": "failed", "error": error, "ttl_at": _queue_ttl_at()}
        )
        firestore_helpers._fs_update_race(
            str(item["race_id"]), {"status": "failed", "current_run_id": None, "last_run_status": "failed"}
        )
        raise RuntimeError(error) from exc


def _current_run_is_terminal_or_missing(db: Any, run_id: str) -> bool:
    try:
        run_doc = db.collection("pipeline_runs").document(run_id).get()
        run_data = firestore_helpers._doc_to_plain(run_doc)
    except Exception:
        return False
    if run_data is None:
        return True
    return run_data.get("status") in _TERMINAL_STATUSES


def _is_run_actually_active(db: Any, run_id: str) -> bool:
    """Return True only when run + queue docs both indicate active work."""
    try:
        run_doc = db.collection("pipeline_runs").document(str(run_id)).get()
        run_data = firestore_helpers._doc_to_plain(run_doc)
    except Exception:
        return False
    if not run_data or run_data.get("status") not in _ACTIVE_STATUSES:
        return False
    try:
        queue_docs = db.collection("pipeline_queue").where("run_id", "==", str(run_id)).limit(20).stream()
        return any((doc.to_dict() or {}).get("status") in _ACTIVE_STATUSES for doc in queue_docs)
    except Exception:
        return False


def _self_heal_stale_active_race(db: Any, race_id: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    """Clear stale queued/running blockers so a new queue request can proceed."""
    status = race_data.get("status")
    if status not in _ACTIVE_STATUSES:
        return race_data

    run_id = race_data.get("current_run_id")
    if not run_id:
        return race_data

    if _is_run_actually_active(db, str(run_id)):
        return race_data

    fallback_status = (
        "published" if race_data.get("published_at") else ("draft" if race_data.get("draft_updated_at") else "failed")
    )
    update = {"status": fallback_status, "current_run_id": None}
    firestore_helpers._fs_update_race(race_id, update)
    return {**race_data, **update}


def _normalize_continuation_ancestors(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Do not report parent queue items as active after a continuation exists."""
    parent_item_ids = {item.get("parent_queue_item_id") for item in items if item.get("parent_queue_item_id")}
    parent_run_ids = {item.get("parent_run_id") for item in items if item.get("parent_run_id")}
    normalized = []
    for item in items:
        next_item = dict(item)
        is_parent = next_item.get("id") in parent_item_ids or next_item.get("run_id") in parent_run_ids
        if is_parent and next_item.get("status") in ("pending", "running"):
            next_item["status"] = "continued"
        normalized.append(next_item)
    return normalized


def _normalize_terminal_run_items(db: Any, items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Mirror authoritative run/race state onto stale active queue items."""
    runs_ref = db.collection("pipeline_runs")
    queue_ref = db.collection("pipeline_queue")
    races_ref = db.collection("races")
    normalized = []
    for item in items:
        next_item = dict(item)
        if next_item.get("status") in _ACTIVE_STATUSES and next_item.get("run_id"):
            updates = None
            try:
                run_doc = runs_ref.document(str(next_item["run_id"])).get()
                run_data = firestore_helpers._doc_to_plain(run_doc)
            except Exception:
                run_data = None
            run_status = (run_data or {}).get("status")
            if run_status in _TERMINAL_STATUSES:
                updates = {"status": run_status, "ttl_at": _queue_ttl_at()}
                for field in ("completed_at", "error", "artifact_id", "duration_ms"):
                    if (run_data or {}).get(field) is not None:
                        updates[field] = run_data[field]
            elif next_item.get("race_id"):
                try:
                    race_doc = races_ref.document(str(next_item["race_id"])).get()
                    race_data = firestore_helpers._doc_to_plain(race_doc)
                except Exception:
                    race_data = None
                race_status = (race_data or {}).get("status")
                current_run_id = (race_data or {}).get("current_run_id")
                if race_status in _INACTIVE_RACE_STATUSES and current_run_id and current_run_id != next_item.get("run_id"):
                    if _current_run_is_terminal_or_missing(db, str(current_run_id)):
                        firestore_helpers._fs_update_race(str(next_item["race_id"]), {"current_run_id": None})
                    else:
                        updates = {
                            "status": "cancelled",
                            "error": f"Superseded by race current_run_id {current_run_id}",
                            "ttl_at": _queue_ttl_at(),
                        }
            if updates:
                next_item.update(updates)
                item_id = next_item.get("id")
                if item_id:
                    try:
                        queue_ref.document(str(item_id)).update(updates)
                    except Exception:
                        logger.exception("Unable to persist reconciled queue item %s", item_id)
        normalized.append(next_item)
    return normalized


@router.get("/steps", dependencies=[Depends(verify_token)])
async def list_steps() -> Dict[str, Any]:
    """Return the ordered list of available pipeline steps."""
    return {"steps": _PIPELINE_STEPS, "step_details": _PIPELINE_STEP_DETAILS}


@router.get("/api/queue", dependencies=[Depends(verify_token)])
async def get_queue(active_only: bool = False, limit: int = 200) -> Dict[str, Any]:
    """List queue items from Firestore.

    When ``active_only=true``, only pending/running items are returned.
    """
    db = firestore_helpers._get_fs()
    limit = max(1, min(limit, 500))
    query = db.collection("pipeline_queue")
    if active_only:
        query = query.where("status", "in", sorted(_ACTIVE_STATUSES))
    docs = query.order_by("created_at", direction="DESCENDING").limit(limit).stream()
    items = [firestore_helpers._doc_to_plain(d) for d in docs]
    items = [i for i in items if i is not None]
    items.reverse()
    items = _normalize_continuation_ancestors(items)
    items = _normalize_terminal_run_items(db, items)
    if active_only:
        items = [item for item in items if item.get("status") in _ACTIVE_STATUSES]
    running = sum(1 for i in items if i.get("status") == "running")
    pending = sum(1 for i in items if i.get("status") == "pending")
    return {"items": items, "running": running > 0, "pending": pending}


@router.post("/api/races/queue", dependencies=[Depends(verify_token)])
async def queue_races(request: RaceQueueRequest) -> Dict[str, Any]:
    """Queue races for local Docker, Cloud Run Jobs, or the temporary CF fallback."""
    db = firestore_helpers._get_fs()
    options = request.options.model_dump(exclude_none=True) if request.options else {}
    added = []
    errors = []
    seen_race_ids = set()

    for raw_id in request.race_ids:
        race_id = raw_id.strip()
        if not race_id:
            continue
        if race_id in seen_race_ids:
            errors.append({"race_id": race_id, "error": "Duplicate race_id in request"})
            continue
        seen_race_ids.add(race_id)
        try:
            validate_race_id(race_id)
        except HTTPException:
            errors.append({"race_id": race_id, "error": "Invalid race_id format"})
            continue
        try:
            from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore

            race_doc = db.collection("races").document(race_id).get()
            if getattr(race_doc, "exists", False) is True:
                race_data = race_doc.to_dict() or {}
                race_data = _self_heal_stale_active_race(db, race_id, race_data)
                if race_data.get("status") in ("queued", "running"):
                    errors.append({"race_id": race_id, "error": f"Race is already {race_data.get('status')}"})
                    continue

            item_id = str(uuid.uuid4())
            run_id = str(uuid.uuid4())
            item = {
                "id": item_id,
                "race_id": race_id,
                "run_id": run_id,
                "options": options,
                "status": "pending",
                "is_continuation": False,
                "runner": (options or {}).get("runner") or _default_runner(),
                "created_at": SERVER_TIMESTAMP,
            }
            db.collection("pipeline_queue").document(item_id).set(item)
            firestore_helpers._fs_update_race(race_id, {"status": "queued", "current_run_id": run_id})
            dispatch = _dispatch_if_cloud_run(db, item)
            added.append(
                {
                    "id": item_id,
                    "race_id": race_id,
                    "run_id": run_id,
                    "status": "pending",
                    "runner": item["runner"],
                    "dispatch": dispatch,
                }
            )
        except Exception as exc:
            errors.append({"race_id": race_id, "error": str(exc)})

    return {"added": added, "errors": errors}


@router.delete("/api/queue/finished", dependencies=[Depends(verify_token)])
async def clear_finished_queue() -> Dict[str, Any]:
    """Delete completed/failed/cancelled queue items."""
    db = firestore_helpers._get_fs()
    finished_statuses = {"completed", "failed", "cancelled", "continued"}
    removed = 0
    docs = db.collection("pipeline_queue").where("status", "in", sorted(finished_statuses)).limit(500).stream()
    for doc in docs:
        doc.reference.delete()
        removed += 1
    return {"removed": removed}


@router.delete("/api/queue/pending", dependencies=[Depends(verify_token)])
async def clear_pending_queue() -> Dict[str, Any]:
    """Cancel all pending (not yet started) queue items."""
    db = firestore_helpers._get_fs()
    removed = 0
    docs = db.collection("pipeline_queue").where("status", "==", "pending").limit(500).stream()
    for doc in docs:
        data = doc.to_dict() or {}
        doc.reference.update({"status": "cancelled", "lease_owner": None, "lease_expires_at": None, "ttl_at": _queue_ttl_at()})
        removed += 1
        race_id = data.get("race_id")
        if race_id:
            firestore_helpers._fs_update_race(race_id, {"status": "idle", "current_run_id": None})
    return {"removed": removed}


@router.delete("/api/queue/{item_id}", dependencies=[Depends(verify_token)])
async def remove_queue_item(item_id: str, force: bool = False) -> Dict[str, Any]:
    """Cancel or remove a specific queue item.

    When ``force=true`` this endpoint always deletes the queue document, even
    if the item is currently running. This matches admin UI recovery behavior
    for stuck queue items.
    """
    db = firestore_helpers._get_fs()
    doc = db.collection("pipeline_queue").document(item_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Queue item not found")
    data = doc.to_dict() or {}
    status = data.get("status", "")
    race_id = data.get("race_id")

    if force:
        doc.reference.delete()
        if race_id:
            firestore_helpers._fs_update_race(race_id, {"status": "cancelled", "current_run_id": None})
        return {"ok": True, "action": "force_removed", "id": item_id}

    if status == "pending":
        doc.reference.update({"status": "cancelled", "lease_owner": None, "lease_expires_at": None, "ttl_at": _queue_ttl_at()})
        if race_id:
            firestore_helpers._fs_update_race(race_id, {"status": "idle", "current_run_id": None})
        return {"ok": True, "action": "cancelled", "id": item_id}
    elif status in ("completed", "failed", "cancelled", "continued"):
        doc.reference.delete()
        return {"ok": True, "action": "removed", "id": item_id}
    else:
        # running — mark cancelled; CF will check at next step boundary
        doc.reference.update({"status": "cancelled", "lease_owner": None, "lease_expires_at": None, "ttl_at": _queue_ttl_at()})
        if race_id:
            firestore_helpers._fs_update_race(race_id, {"status": "cancelled", "current_run_id": None})
        return {"ok": True, "action": "cancelled", "id": item_id}
