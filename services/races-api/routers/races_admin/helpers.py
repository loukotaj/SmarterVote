"""Shared helpers for the race-record admin endpoints.

These functions reconcile Firestore race/run/queue state against GCS storage
and are used across the records, drafts, and run-history endpoint modules in
this package.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import firestore_helpers
import gcs_helpers
from fastapi import HTTPException, Request
from routers.utils import _coerce_datetime, _queue_ttl_at

from shared.pipeline_config import RetentionConfig
from shared.race_catalog import build_race_summary_fields

STALE_ACTIVE_RUN_SECONDS = int(os.getenv("STALE_ACTIVE_RUN_SECONDS", "7200"))
_RETENTION = RetentionConfig.from_env()


def _latest_activity_at(data: Dict[str, Any]) -> datetime | None:
    for key in ("lease_renewed_at", "progress_updated_at", "started_at", "created_at", "updated_at"):
        parsed = _coerce_datetime(data.get(key))
        if parsed:
            return parsed
    return None


def _active_doc_is_fresh(data: Dict[str, Any], now: datetime) -> bool:
    """Return True when a pending/running queue or run doc is recent enough."""
    if data.get("status") not in ("pending", "running"):
        return False
    lease_expires_at = _coerce_datetime(data.get("lease_expires_at"))
    if data.get("status") == "running" and lease_expires_at and lease_expires_at > now:
        return True
    activity_at = _latest_activity_at(data)
    if activity_at is None:
        # Old docs without timestamps are not strong evidence that a Cloud
        # Function is still alive.
        return False
    return now - activity_at <= timedelta(seconds=STALE_ACTIVE_RUN_SECONDS)


def _derive_storage_status(race_id: str, race_data: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    has_published = gcs_helpers._gcs_get_race_json(race_id, "races") is not None
    has_draft = gcs_helpers._gcs_get_race_json(race_id, "drafts") is not None
    new_status = "published" if has_published else ("draft" if has_draft else "failed")
    update: Dict[str, Any] = {
        "status": new_status,
        "current_run_id": None,
        "last_run_status": "failed" if new_status == "failed" else race_data.get("last_run_status"),
        "draft_updated_at": race_data.get("draft_updated_at") if has_draft else None,
    }
    if not has_published:
        update["published_at"] = None
    return new_status, update


def _derive_inactive_storage_status(race_id: str, race_data: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Derive inactive status updates from positive storage evidence only."""
    has_published = gcs_helpers._gcs_get_race_json(race_id, "races") is not None
    has_draft = gcs_helpers._gcs_get_race_json(race_id, "drafts") is not None
    current_status = race_data.get("status")

    # Only apply status changes when storage provides positive evidence.
    # This avoids destructive downgrades during transient storage failures.
    new_status = str(current_status)
    update: Dict[str, Any] = {}
    if has_published:
        new_status = "published"
        if current_status != "published":
            update["status"] = "published"
            update["current_run_id"] = None
    elif has_draft:
        new_status = "draft"
        if current_status != "draft":
            update["status"] = "draft"
            update["current_run_id"] = None
        update["published_at"] = None
        update["draft_updated_at"] = race_data.get("draft_updated_at")

    return new_status, update


def _catalog_update_from_storage(race_id: str) -> Dict[str, Any] | None:
    published_data = gcs_helpers._gcs_get_race_json(race_id, "races")
    draft_data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
    if not isinstance(published_data, dict) and not isinstance(draft_data, dict):
        return None

    base_data = draft_data if isinstance(draft_data, dict) else published_data
    update: Dict[str, Any] = {
        "status": "published" if isinstance(published_data, dict) else "draft",
        "current_run_id": None,
        **build_race_summary_fields(race_id, base_data or {}),
    }

    if isinstance(published_data, dict):
        update.update(firestore_helpers._fs_build_published_catalog_fields(race_id, published_data))
    else:
        update.update(
            {
                "published_at": None,
                "published_updated_utc": None,
                "published_candidate_count": None,
                "published_quality_grade": None,
            }
        )

    if isinstance(draft_data, dict):
        update.update(firestore_helpers._fs_build_draft_catalog_fields(race_id, draft_data))
    else:
        update.update(
            {
                "draft_updated_at": None,
                "draft_updated_utc": None,
                "draft_candidate_count": None,
                "draft_quality_grade": None,
            }
        )

    return update


def _backfill_catalog_from_storage(race_id: str) -> Dict[str, Any] | None:
    update = _catalog_update_from_storage(race_id)
    if update is None:
        return None
    firestore_helpers._fs_update_race(race_id, update)
    return update


def _run_is_terminal_or_missing(db: Any, run_id: str) -> bool:
    try:
        run_doc = db.collection("pipeline_runs").document(run_id).get()
    except Exception:
        return False
    if not getattr(run_doc, "exists", False):
        return True
    run_data = run_doc.to_dict() or {}
    return run_data.get("status") in ("completed", "failed", "cancelled", "continued")


def _is_run_actually_active(db: Any, run_id: str) -> bool:
    """Return True only when run + queue docs both indicate active work."""
    run_ref = db.collection("pipeline_runs").document(str(run_id))
    run_doc = run_ref.get()
    if not run_doc.exists:
        return False
    run_data = run_doc.to_dict() or {}
    if run_data.get("status") not in ("pending", "running"):
        return False
    queue_docs = db.collection("pipeline_queue").where("run_id", "==", str(run_id)).stream()
    return any((doc.to_dict() or {}).get("status") in ("pending", "running") for doc in queue_docs)


def _self_heal_stale_active_race(db: Any, race_id: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    """Clear stale queued/running blockers so a new run request can proceed."""
    status = race_data.get("status")
    if status not in ("queued", "running"):
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


def _recheck_race_status(db: Any, race_id: str, race_data: Dict[str, Any]) -> tuple[Dict[str, Any] | None, bool]:
    """Reconcile one race record and return its latest Firestore shape."""
    current_status = race_data.get("status", "idle")
    updated = False
    reconciled_view: Dict[str, Any] | None = None
    if current_status in ("running", "queued"):
        run_id = race_data.get("current_run_id")
        run_actually_active = False
        run_ref = None
        now = datetime.now(timezone.utc)
        if run_id:
            run_ref = db.collection("pipeline_runs").document(run_id)
            run_doc = run_ref.get()
            if run_doc.exists:
                run_actually_active = _active_doc_is_fresh(run_doc.to_dict() or {}, now)
                queue_docs = db.collection("pipeline_queue").where("run_id", "==", run_id).stream()
                active_queue_docs = [doc for doc in queue_docs if _active_doc_is_fresh(doc.to_dict() or {}, now)]
                # A current worker lease is stronger liveness evidence than a
                # quiet pipeline_runs document during a long model/tool call.
                run_actually_active = (
                    run_actually_active
                    and bool(active_queue_docs)
                    or any(
                        (
                            _coerce_datetime((doc.to_dict() or {}).get("lease_expires_at"))
                            or datetime.min.replace(tzinfo=timezone.utc)
                        )
                        > now
                        for doc in active_queue_docs
                    )
                )
            else:
                # If pipeline_run doc doesn't exist yet (e.g. pending in queue), the run is active if the queue doc is active and fresh
                queue_docs = db.collection("pipeline_queue").where("run_id", "==", run_id).stream()
                active_queue_docs = [doc for doc in queue_docs if _active_doc_is_fresh(doc.to_dict() or {}, now)]
                run_actually_active = bool(active_queue_docs)
        if not run_actually_active:
            _new_status, update = _derive_storage_status(race_id, race_data)
            if run_ref is not None:
                try:
                    run_ref.update(
                        {
                            "status": "failed",
                            "error": f"Marked stale by recheck after {STALE_ACTIVE_RUN_SECONDS} seconds without activity",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except Exception as exc:
                    logging.warning("Failed to mark stale run %s failed: %s", run_id, exc)
            if run_id:
                for doc in db.collection("pipeline_queue").where("run_id", "==", run_id).stream():
                    try:
                        data = doc.to_dict() or {}
                        if data.get("status") in ("pending", "running"):
                            doc.reference.update(
                                {
                                    "status": "failed",
                                    "error": "Marked stale by race recheck",
                                    "completed_at": datetime.now(timezone.utc).isoformat(),
                                    "ttl_at": _queue_ttl_at(),
                                }
                            )
                    except Exception as exc:
                        logging.warning("Failed to mark stale queue item for %s failed: %s", run_id, exc)
            firestore_helpers._fs_update_race(race_id, update)
            updated = True
            reconciled_view = {**race_data, **update}
    elif current_status in ("draft", "published", "empty", "failed", "cancelled"):
        update: Dict[str, Any] = {}

        catalog_update = _catalog_update_from_storage(race_id)
        if catalog_update:
            update.update(catalog_update)

        expected_status, storage_update = _derive_inactive_storage_status(race_id, race_data)
        if current_status != expected_status:
            update.update(storage_update)

        current_run_id = race_data.get("current_run_id")
        if current_run_id:
            run_id = str(current_run_id)
            if _run_is_terminal_or_missing(db, run_id):
                update["current_run_id"] = None
            else:
                # Do not clear current_run_id if it still points to a live run.
                update.pop("current_run_id", None)

        if update:
            firestore_helpers._fs_update_race(race_id, update)
            updated = True
            reconciled_view = {**race_data, **update}
    updated_doc = db.collection("races").document(race_id).get()
    latest = firestore_helpers._doc_to_plain(updated_doc)
    if latest is not None and not latest.get("race_id"):
        latest["race_id"] = race_id
    if updated and reconciled_view is not None:
        if latest is None:
            return reconciled_view, updated
        return {**latest, **reconciled_view}, updated
    return latest, updated


def _race_summary(data: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    """Build the admin race summary shape expected by the web dashboard."""
    summary = build_race_summary_fields(fallback_id, data)
    return {
        "id": summary.get("race_id") or fallback_id,
        "title": summary.get("title"),
        "office": summary.get("office"),
        "jurisdiction": summary.get("jurisdiction"),
        "state": summary.get("state"),
        "election_date": summary.get("election_date") or "",
        "updated_utc": summary.get("updated_utc") or "",
        "candidates": summary.get("candidates") or [],
        "agent_metrics": summary.get("agent_metrics"),
    }


def _grade_from_race_data(data: Dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    validation_grade = data.get("validation_grade")
    if not isinstance(validation_grade, dict):
        return None
    grade = validation_grade.get("grade")
    return str(grade) if grade else None


def _candidate_count_from_race_data(data: Dict[str, Any] | None) -> int | None:
    if not isinstance(data, dict):
        return None
    candidates = data.get("candidates")
    return len(candidates) if isinstance(candidates, list) else None


def _newer_iso(left: str | None, right: str | None) -> bool:
    left_at = _coerce_datetime(left)
    right_at = _coerce_datetime(right)
    if left_at and right_at:
        return left_at > right_at
    return bool(left and left != right)


def _apply_catalog_view(race: Dict[str, Any]) -> Dict[str, Any]:
    draft_exists = bool(race.get("draft_updated_at")) or race.get("status") == "draft"
    published_exists = bool(race.get("published_at")) or bool(race.get("published_updated_utc"))
    draft_updated = race.get("draft_updated_utc") or race.get("draft_updated_at")
    published_updated = race.get("published_updated_utc") or race.get("published_at")

    race["draft_exists"] = draft_exists
    race["published_exists"] = published_exists
    race["has_unpublished_changes"] = bool(
        draft_exists and (not published_exists or _newer_iso(draft_updated, published_updated))
    )

    # Normalize stale Firestore status from catalog/storage evidence so UI listings
    # don't show "empty" for races that clearly have draft/published data.
    current_status = str(race.get("status") or "")
    if current_status not in ("queued", "running"):
        if published_exists:
            race["status"] = "published"
        elif draft_exists:
            race["status"] = "draft"
        elif current_status in ("published", "draft"):
            race["status"] = "empty"

    if published_exists:
        race["quality_grade"] = race.get("published_quality_grade")
        if race.get("published_candidate_count") is not None:
            race["candidate_count"] = race.get("published_candidate_count")
        if published_updated:
            race["public_updated_utc"] = published_updated
    elif draft_exists:
        race["quality_grade"] = race.get("draft_quality_grade")
        if race.get("draft_candidate_count") is not None:
            race["candidate_count"] = race.get("draft_candidate_count")

    return race


def _assert_publishable_race(data: Dict[str, Any]) -> None:
    """Block publishing drafts that the review gate explicitly failed."""
    try:
        gcs_helpers._assert_publishable_race(data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc).replace("Race failed", "Draft failed")) from exc


def _published_race_update() -> Dict[str, Any]:
    return {
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "draft_updated_at": None,
        "current_run_id": None,
    }


def _run_completed_at(data: Dict[str, Any]) -> datetime | None:
    return (
        _coerce_datetime(data.get("completed_at"))
        or _coerce_datetime(data.get("updated_at"))
        or _coerce_datetime(data.get("started_at"))
    )


def _pipeline_run_stats(db: Any) -> Dict[str, Dict[str, Any]]:
    """Aggregate run counts from canonical pipeline_runs docs for the races table."""
    stats: Dict[str, Dict[str, Any]] = {}
    runs_ref = db.collection("pipeline_runs")
    used_projection = False
    try:
        selected_ref = runs_ref.select(["race_id", "status", "started_at", "completed_at", "updated_at", "payload.race_id"])
        docs = selected_ref.stream()
        used_projection = True
    except Exception as exc:
        logging.warning("Falling back to full pipeline_runs scan for run stats: %s", exc)
        try:
            docs = runs_ref.stream()
        except Exception as fallback_exc:
            logging.warning("Failed to aggregate pipeline run counts: %s", fallback_exc)
            return stats

    for doc in docs:
        data = firestore_helpers._doc_to_plain(doc)
        if not data:
            continue
        race_id = data.get("race_id")
        if not race_id:
            payload = data.get("payload")
            if isinstance(payload, dict):
                race_id = payload.get("race_id")
        if not race_id:
            continue
        item = stats.setdefault(str(race_id), {"total_runs": 0})
        item["total_runs"] += 1
        completed_at = _run_completed_at(data)
        existing_at = _coerce_datetime(item.get("last_run_at"))
        if completed_at and (existing_at is None or completed_at > existing_at):
            item["last_run_at"] = completed_at.isoformat()
            item["last_run_id"] = data.get("run_id") or getattr(doc, "id", None)
            item["last_run_status"] = data.get("status")

    if stats or not used_projection:
        return stats

    try:
        docs = runs_ref.stream()
    except Exception as exc:
        logging.warning("Failed full pipeline_runs fallback after empty projection: %s", exc)
        return stats

    for doc in docs:
        data = firestore_helpers._doc_to_plain(doc)
        if not data:
            continue
        race_id = data.get("race_id")
        if not race_id:
            payload = data.get("payload")
            if isinstance(payload, dict):
                race_id = payload.get("race_id")
        if not race_id:
            continue
        item = stats.setdefault(str(race_id), {"total_runs": 0})
        item["total_runs"] += 1
        completed_at = _run_completed_at(data)
        existing_at = _coerce_datetime(item.get("last_run_at"))
        if completed_at and (existing_at is None or completed_at > existing_at):
            item["last_run_at"] = completed_at.isoformat()
            item["last_run_id"] = data.get("run_id") or getattr(doc, "id", None)
            item["last_run_status"] = data.get("status")
    return stats


def _clear_public_race_cache(request: Request) -> None:
    """Clear the public /races cache after admin storage mutations."""
    service = getattr(request.app.state, "publish_service", None)
    clear_cache = getattr(service, "clear_cache", None)
    if callable(clear_cache):
        clear_cache()
