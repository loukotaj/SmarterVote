"""Race record CRUD, draft, publish, and version endpoints."""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import firestore_helpers
import gcs_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException, Request
from request_models import BatchPublishRequest, RaceQueueRequest, RunOptions, validate_race_id

router = APIRouter()

STALE_ACTIVE_RUN_SECONDS = int(os.getenv("STALE_ACTIVE_RUN_SECONDS", "7200"))


def _coerce_datetime(value: Any) -> datetime | None:
    """Parse Firestore timestamps and ISO strings into aware datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _latest_activity_at(data: Dict[str, Any]) -> datetime | None:
    for key in ("progress_updated_at", "started_at", "created_at", "updated_at"):
        parsed = _coerce_datetime(data.get(key))
        if parsed:
            return parsed
    return None


def _active_doc_is_fresh(data: Dict[str, Any], now: datetime) -> bool:
    """Return True when a pending/running queue or run doc is recent enough."""
    if data.get("status") not in ("pending", "running"):
        return False
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


def _recheck_race_status(db: Any, race_id: str, race_data: Dict[str, Any]) -> tuple[Dict[str, Any] | None, bool]:
    """Reconcile one race record and return its latest Firestore shape."""
    current_status = race_data.get("status", "idle")
    updated = False
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
            if run_actually_active:
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
                                }
                            )
                    except Exception as exc:
                        logging.warning("Failed to mark stale queue item for %s failed: %s", run_id, exc)
            firestore_helpers._fs_update_race(race_id, update)
            updated = True
    updated_doc = db.collection("races").document(race_id).get()
    return firestore_helpers._doc_to_plain(updated_doc), updated


def _race_summary(data: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    """Build the admin race summary shape expected by the web dashboard."""
    candidates = data.get("candidates") or []
    return {
        "id": data.get("id") or fallback_id,
        "title": data.get("title"),
        "office": data.get("office"),
        "jurisdiction": data.get("jurisdiction"),
        "state": data.get("state"),
        "election_date": data.get("election_date") or "",
        "updated_utc": data.get("updated_utc") or "",
        "candidates": [
            {
                "name": c.get("name", ""),
                "party": c.get("party"),
                "incumbent": c.get("incumbent"),
                "image_url": c.get("image_url"),
            }
            for c in candidates
            if isinstance(c, dict)
        ],
        "agent_metrics": data.get("agent_metrics"),
    }


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
    try:
        docs = db.collection("pipeline_runs").stream()
    except Exception as exc:
        logging.warning("Failed to aggregate pipeline run counts: %s", exc)
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


# ---------------------------------------------------------------------------
# Race records (Firestore metadata)
# ---------------------------------------------------------------------------


@router.get("/api/races", dependencies=[Depends(verify_token)])
async def list_all_races() -> Dict[str, Any]:
    """List all race records from Firestore (admin view with status metadata)."""
    db = firestore_helpers._get_fs()
    docs = db.collection("races").limit(500).stream()
    races = [firestore_helpers._doc_to_plain(d) for d in docs]
    races = [r for r in races if r is not None]
    run_stats = _pipeline_run_stats(db)
    draft_id_list = gcs_helpers._gcs_list_race_ids("drafts")
    published_id_list = gcs_helpers._gcs_list_race_ids("races")
    draft_ids = set(draft_id_list or [])
    published_ids = set(published_id_list or [])
    storage_state_known = draft_id_list is not None and published_id_list is not None

    for race in races:
        race_id = race.get("race_id") or race.get("id")
        draft_exists = race_id in draft_ids
        published_exists = race_id in published_ids

        # Storage is the source of truth for publishability. Firestore metadata can
        # drift after failed publishes, deletes, or legacy admin flows.
        status = race.get("status")
        if storage_state_known:
            race["draft_exists"] = draft_exists
            race["published_exists"] = published_exists
        if storage_state_known and status not in ("queued", "running"):
            if published_exists:
                race["status"] = "published"
                if not draft_exists:
                    race["draft_updated_at"] = None
            elif draft_exists:
                race["status"] = "draft"
            elif status in ("draft", "published"):
                race["status"] = "empty"
                race["draft_updated_at"] = None
                race["published_at"] = None
        stats = run_stats.get(str(race_id))
        if stats:
            race["total_runs"] = stats["total_runs"]
            race["last_run_id"] = stats.get("last_run_id")
            race["last_run_at"] = stats.get("last_run_at")
            race["last_run_status"] = stats.get("last_run_status")
        else:
            race["total_runs"] = int(race.get("total_runs") or 0)
    return {"races": races}


@router.get("/api/races/drafts", dependencies=[Depends(verify_token)])
async def list_draft_races() -> Dict[str, Any]:
    """List all draft race summaries from GCS."""
    ids = gcs_helpers._gcs_list_race_ids("drafts")
    races = []
    for race_id in ids or []:
        data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
        if isinstance(data, dict):
            races.append(_race_summary(data, race_id))
    return {"races": races}


@router.post("/api/races/recheck", dependencies=[Depends(verify_token)])
async def recheck_all_race_statuses() -> Dict[str, Any]:
    """Re-derive status for all race records and clear stale active runs."""
    db = firestore_helpers._get_fs()
    docs = db.collection("races").limit(500).stream()
    races: list[Dict[str, Any]] = []
    updated = 0
    for doc in docs:
        race_data = firestore_helpers._doc_to_plain(doc)
        if not race_data:
            continue
        race_id = race_data.get("race_id") or race_data.get("id")
        if not race_id:
            continue
        latest, changed = _recheck_race_status(db, race_id, race_data)
        if latest:
            races.append(latest)
        if changed:
            updated += 1
    return {"message": f"Rechecked {len(races)} races", "checked": len(races), "updated": updated, "races": races}


@router.get("/api/races/{race_id}", dependencies=[Depends(verify_token)])
async def get_race_record(race_id: str) -> Dict[str, Any]:
    """Get a single race record from Firestore."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    doc = db.collection("races").document(race_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data is None:
        raise HTTPException(status_code=404, detail="Race not found")
    return data


@router.delete("/api/races/{race_id}", dependencies=[Depends(verify_token)])
async def delete_race_record(request: Request, race_id: str) -> Dict[str, Any]:
    """Delete a race record and all associated GCS blobs."""
    validate_race_id(race_id)
    gcs_helpers._gcs_delete_race_json(race_id, "races")
    gcs_helpers._gcs_delete_race_json(race_id, "drafts")
    try:
        firestore_helpers._get_fs().collection("races").document(race_id).delete()
    except Exception as exc:
        logging.warning("Firestore delete race %s failed: %s", race_id, exc)
    _clear_public_race_cache(request)
    return {"message": f"Race {race_id} deleted", "id": race_id}


@router.post("/api/races/{race_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_race(race_id: str) -> Dict[str, Any]:
    """Cancel a queued or running race by updating Firestore state."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    race_doc = db.collection("races").document(race_id).get()
    if not race_doc.exists:
        raise HTTPException(status_code=404, detail="Race not found")
    race_data = race_doc.to_dict() or {}
    if race_data.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=400, detail="Race is not queued or running")
    for doc in db.collection("pipeline_queue").where("race_id", "==", race_id).stream():
        d = doc.to_dict() or {}
        if d.get("status") in ("pending", "running"):
            doc.reference.update({"status": "cancelled"})
    run_id = race_data.get("current_run_id")
    if run_id:
        run_ref = db.collection("pipeline_runs").document(run_id)
        run_doc = run_ref.get()
        if run_doc.exists and (run_doc.to_dict() or {}).get("status") in ("pending", "running"):
            run_ref.update({"status": "cancelled"})
    firestore_helpers._fs_update_race(race_id, {"status": "cancelled"})
    return {"message": f"Race {race_id} cancelled"}


@router.post("/api/races/{race_id}/recheck", dependencies=[Depends(verify_token)])
async def recheck_race_status(race_id: str) -> Dict[str, Any]:
    """Re-derive race status from GCS storage state (fixes stuck records)."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    race_doc = db.collection("races").document(race_id).get()
    if not race_doc.exists:
        raise HTTPException(status_code=404, detail="Race not found")
    race_data = race_doc.to_dict() or {}
    latest, _changed = _recheck_race_status(db, race_id, race_data)
    return {"message": f"Race {race_id} rechecked", "race": latest}


@router.post("/api/races/{race_id}/run", dependencies=[Depends(verify_token)])
async def run_race_pipeline(race_id: str, options: RunOptions | None = None) -> Dict[str, Any]:
    """Trigger the pipeline for a race by writing to the Firestore queue."""
    validate_race_id(race_id)
    opts = options.model_dump(exclude_none=True) if options else {}
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore

    db = firestore_helpers._get_fs()
    race_doc = db.collection("races").document(race_id).get()
    if race_doc.exists:
        race_data = race_doc.to_dict() or {}
        if race_data.get("status") in ("queued", "running"):
            raise HTTPException(status_code=409, detail=f"Race is already {race_data.get('status')}")

    item_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    item = {
        "id": item_id,
        "race_id": race_id,
        "run_id": run_id,
        "options": opts,
        "status": "pending",
        "is_continuation": False,
        "created_at": SERVER_TIMESTAMP,
    }
    db.collection("pipeline_queue").document(item_id).set(item)
    firestore_helpers._fs_update_race(race_id, {"status": "queued", "current_run_id": run_id})
    return {"run_id": run_id, "status": "queued", "race_id": race_id}


# ---------------------------------------------------------------------------
# Draft / publish endpoints
# ---------------------------------------------------------------------------


@router.delete("/api/races/{race_id}/draft", dependencies=[Depends(verify_token)])
async def delete_draft_race(race_id: str) -> Dict[str, Any]:
    """Delete a draft race from GCS and update Firestore record."""
    validate_race_id(race_id)
    deleted = gcs_helpers._gcs_delete_race_json(race_id, "drafts")
    if not deleted:
        raise HTTPException(status_code=404, detail="Draft not found")
    has_published = gcs_helpers._gcs_get_race_json(race_id, "races") is not None
    firestore_helpers._fs_update_race(race_id, {"status": "published" if has_published else "empty", "draft_updated_at": None})
    return {"message": f"Draft {race_id} deleted", "id": race_id}


@router.post("/api/races/{race_id}/publish", dependencies=[Depends(verify_token)])
async def publish_race(request: Request, race_id: str) -> Dict[str, Any]:
    """Publish a race (copy draft -> published in GCS)."""
    validate_race_id(race_id)
    data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
    if data is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    _assert_publishable_race(data)
    gcs_helpers._publish_race_gcs(race_id, data)
    firestore_helpers._fs_update_race(race_id, _published_race_update())
    _clear_public_race_cache(request)
    return {"message": f"Race {race_id} published", "id": race_id}


@router.post("/api/races/{race_id}/unpublish", dependencies=[Depends(verify_token)])
async def unpublish_race(request: Request, race_id: str) -> Dict[str, Any]:
    """Remove a race from published (keeps draft)."""
    validate_race_id(race_id)
    has_draft = gcs_helpers._gcs_get_race_json(race_id, "drafts") is not None
    deleted = gcs_helpers._gcs_delete_race_json(race_id, "races")
    if not deleted:
        raise HTTPException(status_code=404, detail="Published race not found")
    firestore_helpers._fs_update_race(
        race_id,
        {
            "status": "draft" if has_draft else "empty",
            "published_at": None,
            "draft_updated_at": datetime.now(timezone.utc).isoformat() if has_draft else None,
        },
    )
    _clear_public_race_cache(request)
    return {"message": f"Race {race_id} unpublished (draft retained)", "id": race_id}


@router.post("/api/races/publish", dependencies=[Depends(verify_token)])
async def batch_publish_races(request: Request, payload: BatchPublishRequest) -> Dict[str, Any]:
    """Publish multiple races at once (draft -> published)."""
    published = []
    errors = []
    for race_id in payload.race_ids:
        try:
            validate_race_id(race_id)
            data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
            if data is None:
                errors.append({"race_id": race_id, "error": "Draft not found"})
                continue
            _assert_publishable_race(data)
            gcs_helpers._publish_race_gcs(race_id, data)
            firestore_helpers._fs_update_race(race_id, _published_race_update())
            published.append(race_id)
        except HTTPException as exc:
            errors.append({"race_id": race_id, "error": exc.detail})
        except Exception as exc:
            errors.append({"race_id": race_id, "error": str(exc)})
    if published:
        _clear_public_race_cache(request)
    return {"published": published, "errors": errors}


# ---------------------------------------------------------------------------
# Race run history endpoints
# ---------------------------------------------------------------------------


@router.get("/api/races/{race_id}/runs", dependencies=[Depends(verify_token)])
async def list_race_runs(race_id: str, limit: int = 20) -> Dict[str, Any]:
    """List runs for a specific race from Firestore."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    sub_docs = (
        db.collection("races")
        .document(race_id)
        .collection("runs")
        .order_by("started_at", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    runs = [firestore_helpers._doc_to_plain(d) for d in sub_docs]
    active_docs = db.collection("pipeline_runs").where("race_id", "==", race_id).stream()
    for d in active_docs:
        data = firestore_helpers._doc_to_plain(d)
        if data and data.get("status") in ("pending", "running"):
            runs.insert(0, data)
    runs = [r for r in runs if r is not None]
    return {"runs": runs[:limit], "count": len(runs[:limit])}


@router.get("/api/races/{race_id}/runs/{run_id}", dependencies=[Depends(verify_token)])
async def get_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Get details of a specific run for a race."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    doc = db.collection("pipeline_runs").document(run_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data:
        return data
    doc = db.collection("races").document(race_id).collection("runs").document(run_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return data


@router.delete("/api/races/{race_id}/runs/{run_id}", dependencies=[Depends(verify_token)])
async def delete_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Cancel or delete a run for a race."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    run_ref = db.collection("pipeline_runs").document(run_id)
    run_doc = run_ref.get()
    if run_doc.exists:
        status = (run_doc.to_dict() or {}).get("status", "")
        if status in ("pending", "running"):
            run_ref.update({"status": "cancelled"})
            for queue_doc in db.collection("pipeline_queue").where("run_id", "==", run_id).stream():
                queue_data = queue_doc.to_dict() or {}
                if queue_data.get("status") in ("pending", "running"):
                    queue_doc.reference.update({"status": "cancelled"})
            race_doc = db.collection("races").document(race_id).get()
            if race_doc.exists and (race_doc.to_dict() or {}).get("status") in ("running", "queued"):
                firestore_helpers._fs_update_race(race_id, {"status": "cancelled"})
            return {"message": "Run cancelled", "run_id": run_id}
        else:
            run_ref.delete()
        return {"message": "Run deleted", "run_id": run_id}
    sub_ref = db.collection("races").document(race_id).collection("runs").document(run_id)
    if sub_ref.get().exists:
        sub_ref.delete()
        return {"message": "Run deleted", "run_id": run_id}
    raise HTTPException(status_code=404, detail="Run not found")


# ---------------------------------------------------------------------------
# Race data endpoints
# ---------------------------------------------------------------------------


@router.get("/api/races/{race_id}/data", dependencies=[Depends(verify_token)])
async def get_race_data(race_id: str, draft: bool = False) -> Dict[str, Any]:
    """Get full race JSON (published or draft)."""
    validate_race_id(race_id)
    prefix = "drafts" if draft else "races"
    label = "Draft" if draft else "Race"
    data = gcs_helpers._gcs_get_race_json(race_id, prefix)
    if data is None:
        raise HTTPException(status_code=404, detail=f"{label} data not found")
    return data


# ---------------------------------------------------------------------------
# Version / restore endpoints
# ---------------------------------------------------------------------------


@router.get("/api/races/{race_id}/versions", dependencies=[Depends(verify_token)])
async def list_race_versions(race_id: str) -> Dict[str, Any]:
    """List retired (archived) versions for a race, newest first."""
    validate_race_id(race_id)
    versions = gcs_helpers._gcs_list_versions(race_id)
    versions.sort(key=lambda v: v.get("archived_at") or "", reverse=True)
    return {"versions": versions, "count": len(versions)}


@router.get("/api/races/{race_id}/versions/{filename}", dependencies=[Depends(verify_token)])
async def get_race_version(race_id: str, filename: str) -> Dict[str, Any]:
    """Return JSON content of a specific retired version."""
    validate_race_id(race_id)
    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid version filename")
    bucket_name = gcs_helpers._GCS_BUCKET
    if not bucket_name:
        raise HTTPException(status_code=503, detail="GCS not configured")
    client = gcs_helpers._get_gcs_admin()
    if client is None:
        raise HTTPException(status_code=503, detail="GCS unavailable")
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(f"retired/{race_id}/{filename}")
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Version not found")
        return json.loads(blob.download_as_text())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GCS error: {exc}") from exc


@router.post("/api/races/{race_id}/versions/{filename}/restore", dependencies=[Depends(verify_token)])
async def restore_version_as_draft(race_id: str, filename: str) -> Dict[str, Any]:
    """Restore a retired version as the active draft."""
    validate_race_id(race_id)
    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid version filename")
    bucket_name = gcs_helpers._GCS_BUCKET
    if not bucket_name:
        raise HTTPException(status_code=503, detail="GCS not configured")
    client = gcs_helpers._get_gcs_admin()
    if client is None:
        raise HTTPException(status_code=503, detail="GCS unavailable")
    try:
        bucket = client.bucket(bucket_name)
        src_blob = bucket.blob(f"retired/{race_id}/{filename}")
        if not src_blob.exists():
            raise HTTPException(status_code=404, detail="Retired version not found")
        version_data = json.loads(src_blob.download_as_text())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GCS read error: {exc}") from exc

    gcs_helpers._gcs_archive_race(race_id, "drafts", "draft")
    gcs_helpers._gcs_put_race_json(race_id, "drafts", version_data)
    firestore_helpers._fs_update_race(
        race_id,
        {"status": "draft", "draft_updated_at": datetime.now(timezone.utc).isoformat()},
    )
    return {"message": f"Retired version restored as draft for {race_id}", "id": race_id, "restored_from": filename}
