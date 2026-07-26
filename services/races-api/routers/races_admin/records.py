"""Race record (Firestore metadata) CRUD, status reconciliation, and run trigger endpoints."""

import logging
import os
import uuid
from typing import Any, Dict

import firestore_helpers
import gcs_helpers
from auth import verify_token
from cloud_run_jobs import dispatch_pipeline_job
from fastapi import APIRouter, Depends, HTTPException, Request
from request_models import RunOptions, validate_race_id
from routers.utils import _queue_ttl_at

from .helpers import (
    _apply_catalog_view,
    _backfill_catalog_from_storage,
    _clear_public_race_cache,
    _pipeline_run_stats,
    _race_summary,
    _recheck_race_status,
    _self_heal_stale_active_race,
)

router = APIRouter()


@router.get("/api/races", dependencies=[Depends(verify_token)])
async def list_all_races(reconcile_active: bool = False) -> Dict[str, Any]:
    """List all race records from Firestore (admin view with catalog metadata)."""
    db = firestore_helpers._get_fs()
    docs = db.collection("races").limit(10000).stream()
    races = []
    for d in docs:
        plain = firestore_helpers._doc_to_plain(d)
        if plain is not None:
            if not plain.get("race_id"):
                plain["race_id"] = d.id
            races.append(plain)

    if reconcile_active:
        reconciled: list[Dict[str, Any]] = []
        for race in races:
            race_id = race.get("race_id") or race.get("id")
            if not race_id:
                reconciled.append(race)
                continue
            if race.get("status") in ("queued", "running") or race.get("current_run_id"):
                latest, _changed = _recheck_race_status(db, str(race_id), race)
                reconciled.append(latest or race)
            else:
                reconciled.append(race)
        races = reconciled

    run_stats = _pipeline_run_stats(db)
    for race in races:
        race_id = race.get("race_id") or race.get("id")
        _apply_catalog_view(race)
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
    """List all draft race summaries from the Firestore race catalog."""
    db = firestore_helpers._get_fs()
    docs = db.collection("races").limit(1000).stream()
    races = []
    for doc in docs:
        data = firestore_helpers._doc_to_plain(doc)
        if not data:
            continue
        if not (data.get("draft_updated_at") or data.get("status") == "draft"):
            continue
        races.append(_race_summary(data, str(data.get("race_id") or data.get("id") or "")))
    return {"races": races}


@router.post("/api/races/recheck", dependencies=[Depends(verify_token)])
async def recheck_all_race_statuses() -> Dict[str, Any]:
    """Re-derive status for all race records and hydrate missing catalog metadata from storage."""
    db = firestore_helpers._get_fs()
    docs = db.collection("races").limit(1000).stream()
    races: list[Dict[str, Any]] = []
    updated = 0
    seen_race_ids: set[str] = set()
    for doc in docs:
        race_data = firestore_helpers._doc_to_plain(doc)
        if not race_data:
            continue
        race_id = race_data.get("race_id") or race_data.get("id") or doc.id
        if not race_data.get("race_id"):
            race_data["race_id"] = race_id
        seen_race_ids.add(str(race_id))
        latest, changed = _recheck_race_status(db, race_id, race_data)
        if latest:
            races.append(latest)
        if changed:
            updated += 1

    storage_ids = set(gcs_helpers._gcs_list_race_ids("races") or [])
    storage_ids.update(gcs_helpers._gcs_list_race_ids("drafts") or [])
    for race_id in sorted(storage_ids - seen_race_ids):
        update = _backfill_catalog_from_storage(race_id)
        if update is None:
            continue
        races.append({"race_id": race_id, **update})
        updated += 1
    return {"message": f"Rechecked {len(races)} races", "checked": len(races), "updated": updated, "races": races}


@router.get("/api/races/{race_id}", dependencies=[Depends(verify_token)])
async def get_race_record(race_id: str, reconcile: bool = True) -> Dict[str, Any]:
    """Get a single race record from Firestore."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    doc = db.collection("races").document(race_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data is None:
        raise HTTPException(status_code=404, detail="Race not found")
    if not data.get("race_id"):
        data["race_id"] = race_id
    if reconcile:
        latest, _changed = _recheck_race_status(db, race_id, data)
        if latest is not None:
            data = latest
            if not data.get("race_id"):
                data["race_id"] = race_id
    _apply_catalog_view(data)
    return data


@router.delete("/api/races/{race_id}", dependencies=[Depends(verify_token)])
async def delete_race_record(request: Request, race_id: str) -> Dict[str, Any]:
    """Delete a race record and all associated GCS blobs."""
    validate_race_id(race_id)
    gcs_helpers._gcs_delete_race_json(race_id, "races")
    gcs_helpers._gcs_delete_race_json(race_id, "drafts")
    gcs_helpers.update_gcs_summaries_json({race_id: None})
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
            doc.reference.update(
                {"status": "cancelled", "lease_owner": None, "lease_expires_at": None, "ttl_at": _queue_ttl_at()}
            )
    run_id = race_data.get("current_run_id")
    if run_id:
        run_ref = db.collection("pipeline_runs").document(run_id)
        run_doc = run_ref.get()
        if run_doc.exists and (run_doc.to_dict() or {}).get("status") in ("pending", "running"):
            run_ref.update({"status": "cancelled"})
    firestore_helpers._fs_update_race(race_id, {"status": "cancelled", "current_run_id": None})
    return {"message": f"Race {race_id} cancelled"}


@router.post("/api/races/{race_id}/recheck", dependencies=[Depends(verify_token)])
async def recheck_race_status(race_id: str) -> Dict[str, Any]:
    """Re-derive race status from GCS storage state and backfill missing race docs."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    race_doc = db.collection("races").document(race_id).get()
    if not race_doc.exists:
        update = _backfill_catalog_from_storage(race_id)
        if update is None:
            raise HTTPException(status_code=404, detail="Race not found")
        return {"message": f"Race {race_id} rechecked", "race": {"race_id": race_id, **update}}
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
        race_data = _self_heal_stale_active_race(db, race_id, race_data)
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
        "runner": opts.get("runner") or os.getenv("PIPELINE_DEFAULT_RUNNER", "local").strip().lower(),
        "created_at": SERVER_TIMESTAMP,
    }
    db.collection("pipeline_queue").document(item_id).set(item)
    firestore_helpers._fs_update_race(race_id, {"status": "queued", "current_run_id": run_id})
    dispatch = None
    if item["runner"] == "cloud_run":
        try:
            dispatch = dispatch_pipeline_job(item_id)
            db.collection("pipeline_queue").document(item_id).update({"dispatch_status": "submitted", **dispatch})
        except Exception as exc:
            error = f"Cloud Run Job dispatch failed: {exc}"
            db.collection("pipeline_queue").document(item_id).update(
                {"status": "failed", "dispatch_status": "failed", "error": error, "ttl_at": _queue_ttl_at()}
            )
            firestore_helpers._fs_update_race(
                race_id, {"status": "failed", "current_run_id": None, "last_run_status": "failed"}
            )
            raise HTTPException(status_code=503, detail=error) from exc
    return {"run_id": run_id, "status": "queued", "race_id": race_id, "runner": item["runner"], "dispatch": dispatch}
