"""Per-race run history endpoints (list/get/cancel-or-delete a run for one race)."""

from typing import Any, Dict

import firestore_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException
from request_models import validate_race_id
from routers.utils import _queue_ttl_at

from shared.config import (
    FIRESTORE_QUEUE_COLLECTION,
    FIRESTORE_RACE_RUNS_SUBCOLLECTION,
    FIRESTORE_RACES_COLLECTION,
    FIRESTORE_RUNS_COLLECTION,
)

router = APIRouter()


@router.get("/api/races/{race_id}/runs", dependencies=[Depends(verify_token)])
def list_race_runs(race_id: str, limit: int = 20) -> Dict[str, Any]:
    """List archived and canonical runs for a specific race from Firestore."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    limit = max(1, min(limit, 100))
    sub_docs = (
        db.collection(FIRESTORE_RACES_COLLECTION)
        .document(race_id)
        .collection(FIRESTORE_RACE_RUNS_SUBCOLLECTION)
        .order_by("started_at", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    runs_by_id: Dict[str, Dict[str, Any]] = {}
    for d in sub_docs:
        data = firestore_helpers._doc_to_plain(d)
        if data:
            runs_by_id[str(data.get("run_id") or getattr(d, "id", ""))] = data

    canonical_docs = db.collection(FIRESTORE_RUNS_COLLECTION).where("race_id", "==", race_id).stream()
    for d in canonical_docs:
        data = firestore_helpers._doc_to_plain(d)
        if data:
            runs_by_id[str(data.get("run_id") or getattr(d, "id", ""))] = data

    runs = list(runs_by_id.values())
    runs.sort(
        key=lambda run: (
            run.get("status") in ("pending", "running"),
            str(run.get("started_at") or run.get("created_at") or ""),
        ),
        reverse=True,
    )
    return {"runs": runs[:limit], "count": len(runs[:limit])}


@router.get("/api/races/{race_id}/runs/{run_id}", dependencies=[Depends(verify_token)])
def get_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Get details of a specific run for a race."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    doc = db.collection(FIRESTORE_RUNS_COLLECTION).document(run_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data:
        return data
    doc = (
        db.collection(FIRESTORE_RACES_COLLECTION)
        .document(race_id)
        .collection(FIRESTORE_RACE_RUNS_SUBCOLLECTION)
        .document(run_id)
        .get()
    )
    data = firestore_helpers._doc_to_plain(doc)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return data


@router.delete("/api/races/{race_id}/runs/{run_id}", dependencies=[Depends(verify_token)])
def delete_race_run(race_id: str, run_id: str) -> Dict[str, Any]:
    """Cancel or delete a run for a race."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    run_ref = db.collection(FIRESTORE_RUNS_COLLECTION).document(run_id)
    run_doc = run_ref.get()
    if run_doc.exists:
        status = (run_doc.to_dict() or {}).get("status", "")
        if status in ("pending", "running"):
            run_ref.update({"status": "cancelled"})
            for queue_doc in db.collection(FIRESTORE_QUEUE_COLLECTION).where("run_id", "==", run_id).stream():
                queue_data = queue_doc.to_dict() or {}
                if queue_data.get("status") in ("pending", "running"):
                    queue_doc.reference.update({"status": "cancelled", "ttl_at": _queue_ttl_at()})
            race_doc = db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).get()
            if race_doc.exists and (race_doc.to_dict() or {}).get("status") in ("running", "queued"):
                firestore_helpers._fs_update_race(race_id, {"status": "cancelled"})
            return {"message": "Run cancelled", "run_id": run_id}
        else:
            run_ref.delete()
        return {"message": "Run deleted", "run_id": run_id}
    sub_ref = (
        db.collection(FIRESTORE_RACES_COLLECTION)
        .document(race_id)
        .collection(FIRESTORE_RACE_RUNS_SUBCOLLECTION)
        .document(run_id)
    )
    if sub_ref.get().exists:
        sub_ref.delete()
        return {"message": "Run deleted", "run_id": run_id}
    raise HTTPException(status_code=404, detail="Run not found")
