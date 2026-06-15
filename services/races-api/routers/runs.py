"""Run detail and log endpoints.

Runs are stored in Firestore `pipeline_runs` collection by the Cloud Function.
Logs are stored in the `pipeline_runs/{run_id}/logs` subcollection.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import firestore_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()

_ACTIVE_STATUSES = {"pending", "running"}
_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "continued"}
_INACTIVE_RACE_STATUSES = {"draft", "published", "empty", "failed", "cancelled"}
_STALE_ACTIVE_RUN_SECONDS = int(os.getenv("STALE_ACTIVE_RUN_SECONDS", "7200"))


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _latest_activity_at(data: Dict[str, Any]) -> datetime | None:
    for key in ("completed_at", "progress_updated_at", "updated_at", "started_at", "created_at"):
        parsed = _coerce_datetime(data.get(key))
        if parsed:
            return parsed
    return None


def _run_sort_key(run: Dict[str, Any]) -> tuple[datetime, str]:
    activity_at = _latest_activity_at(run) or datetime.min.replace(tzinfo=timezone.utc)
    return (activity_at, str(run.get("run_id") or ""))


def _derive_logical_duration(run: Dict[str, Any]) -> Dict[str, Any]:
    """Use logical run timestamps instead of the final invocation duration."""
    started_at = _coerce_datetime(run.get("started_at"))
    completed_at = _coerce_datetime(run.get("completed_at"))
    if started_at and completed_at and completed_at >= started_at:
        run["duration_ms"] = int((completed_at - started_at).total_seconds() * 1000)
    return run


def _collapse_continuation_chains(runs: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Present legacy continuation documents as one logical run."""
    by_id = {str(run.get("run_id")): run for run in runs if run.get("run_id")}
    parent_by_child = {
        str(run["continuation_run_id"]): str(run["run_id"])
        for run in runs
        if run.get("run_id") and run.get("continuation_run_id")
    }

    def root_id(run_id: str) -> str:
        seen: set[str] = set()
        current = run_id
        while current in parent_by_child and current not in seen:
            seen.add(current)
            current = parent_by_child[current]
        return current

    groups: Dict[str, list[Dict[str, Any]]] = {}
    for run_id, run in by_id.items():
        groups.setdefault(root_id(run_id), []).append(run)

    collapsed: list[Dict[str, Any]] = []
    for logical_run_id, group in groups.items():
        ordered = sorted(group, key=_run_sort_key)
        terminal = [run for run in ordered if run.get("status") != "continued"]
        representative = dict((terminal or ordered)[-1])
        if not terminal:
            next_run_id = representative.get("continuation_run_id")
            representative["status"] = "running"
            if next_run_id:
                representative["run_id"] = str(next_run_id)
        starts = [_coerce_datetime(run.get("started_at")) for run in group]
        starts = [value for value in starts if value is not None]
        ends = [_coerce_datetime(run.get("completed_at") or run.get("continued_at")) for run in group]
        ends = [value for value in ends if value is not None]
        representative["logical_run_id"] = logical_run_id
        representative["continuation_count"] = max(
            int(representative.get("continuation_count") or 0),
            len(group) - 1,
        )
        invocation_run_ids = [str(run["run_id"]) for run in ordered]
        if representative.get("run_id") not in invocation_run_ids:
            invocation_run_ids.append(str(representative["run_id"]))
        representative["invocation_run_ids"] = invocation_run_ids
        if starts:
            representative["started_at"] = min(starts).isoformat()
        if starts and ends:
            representative["duration_ms"] = int((max(ends) - min(starts)).total_seconds() * 1000)
        collapsed.append(_derive_logical_duration(representative))
    return collapsed


def _is_stale_active_run(data: Dict[str, Any], now: datetime) -> bool:
    if data.get("status") not in _ACTIVE_STATUSES:
        return False
    activity_at = _latest_activity_at(data)
    if activity_at is None:
        return True
    return now - activity_at > timedelta(seconds=_STALE_ACTIVE_RUN_SECONDS)


def _current_run_is_terminal_or_missing(db: Any, run_id: str) -> bool:
    try:
        run_doc = db.collection("pipeline_runs").document(run_id).get()
        run_data = firestore_helpers._doc_to_plain(run_doc)
    except Exception:
        return False
    if run_data is None:
        return True
    return run_data.get("status") in _TERMINAL_STATUSES


def _normalize_active_run(db: Any, run: Dict[str, Any], now: datetime) -> Dict[str, Any] | None:
    """Self-heal stale/superseded active run docs before returning /runs/active."""
    run_id = run.get("run_id")
    if not run_id or run.get("status") not in _ACTIVE_STATUSES:
        return run

    runs_ref = db.collection("pipeline_runs")
    queue_ref = db.collection("pipeline_queue")
    race_id = run.get("race_id") or (run.get("payload") or {}).get("race_id")

    if race_id:
        try:
            race_doc = db.collection("races").document(str(race_id)).get()
            race_data = firestore_helpers._doc_to_plain(race_doc)
        except Exception:
            race_data = None
        if race_data:
            race_status = race_data.get("status")
            current_run_id = race_data.get("current_run_id")
            if race_status in _INACTIVE_RACE_STATUSES and current_run_id and current_run_id != run_id:
                if _current_run_is_terminal_or_missing(db, str(current_run_id)):
                    firestore_helpers._fs_update_race(str(race_id), {"current_run_id": None})
                    return run
                update = {"status": "cancelled", "error": f"Superseded by race current_run_id {current_run_id}"}
                try:
                    runs_ref.document(str(run_id)).update(update)
                except Exception:
                    pass
                for queue_doc in queue_ref.where("run_id", "==", run_id).limit(20).stream():
                    queue_data = queue_doc.to_dict() or {}
                    if queue_data.get("status") in _ACTIVE_STATUSES:
                        try:
                            queue_doc.reference.update(update)
                        except Exception:
                            pass
                return None

    if _is_stale_active_run(run, now):
        update = {
            "status": "failed",
            "error": f"Marked stale by active run listing after {_STALE_ACTIVE_RUN_SECONDS} seconds without activity",
            "completed_at": now.isoformat(),
        }
        try:
            runs_ref.document(str(run_id)).update(update)
        except Exception:
            pass
        for queue_doc in queue_ref.where("run_id", "==", run_id).limit(20).stream():
            queue_data = queue_doc.to_dict() or {}
            if queue_data.get("status") in _ACTIVE_STATUSES:
                try:
                    queue_doc.reference.update(
                        {
                            "status": "failed",
                            "error": "Marked stale by active run listing",
                            "completed_at": now.isoformat(),
                        }
                    )
                except Exception:
                    pass
        return None

    return run


def _log_sort_key(entry: Dict[str, Any]) -> tuple[float, str]:
    """Return a stable ascending sort key for mixed legacy/new log schemas."""
    ts_val = entry.get("timestamp")
    if isinstance(ts_val, str):
        try:
            return (datetime.fromisoformat(ts_val.replace("Z", "+00:00")).timestamp(), "")
        except ValueError:
            pass

    legacy_ts = entry.get("ts")
    if isinstance(legacy_ts, (int, float)):
        return (float(legacy_ts), "")

    # Firestore doc IDs from FirestoreLogger are millisecond-prefix sortable.
    return (0.0, str(entry.get("id") or ""))


@router.get("/runs", dependencies=[Depends(verify_token)])
async def list_runs(limit: int = 50) -> Dict[str, Any]:
    """List recent pipeline runs from Firestore, newest first.

    Firestore ordering can miss active continuation docs when `started_at` has
    mixed legacy string and server timestamp values. Merge in the active query so
    dashboards always show the true active count and current parallel work.
    """

    limit = max(1, min(limit, 500))

    def _ordered_runs(field: str) -> list[Dict[str, Any]]:
        try:
            docs = db.collection("pipeline_runs").order_by(field, direction="DESCENDING").limit(limit).stream()
            return [r for r in (firestore_helpers._doc_to_plain(d) for d in docs) if r is not None]
        except Exception:
            return []

    db = firestore_helpers._get_fs()
    runs: list[Dict[str, Any]] = []
    for field in ("progress_updated_at", "completed_at", "updated_at", "started_at"):
        runs.extend(_ordered_runs(field))

    active_docs = db.collection("pipeline_runs").where("status", "in", ["pending", "running"]).limit(500).stream()
    active_runs = [firestore_helpers._doc_to_plain(d) for d in active_docs]
    active_runs = [r for r in active_runs if r is not None]
    now = datetime.now(timezone.utc)
    active_runs = [r for r in (_normalize_active_run(db, r, now) for r in active_runs) if r is not None]

    merged: Dict[str, Dict[str, Any]] = {}
    for run in runs + active_runs:
        run_id = run.get("run_id")
        if run_id:
            merged[str(run_id)] = run

    ordered = sorted(_collapse_continuation_chains(list(merged.values())), key=_run_sort_key, reverse=True)
    active = sum(1 for r in active_runs if r.get("status") in _ACTIVE_STATUSES)
    return {"runs": ordered[:limit], "active_count": active, "total_count": len(ordered)}


@router.get("/runs/active", dependencies=[Depends(verify_token)])
async def list_active_runs() -> Dict[str, Any]:
    """List currently running or pending pipeline runs."""
    db = firestore_helpers._get_fs()
    docs = db.collection("pipeline_runs").where("status", "in", ["pending", "running"]).limit(500).stream()
    runs = [firestore_helpers._doc_to_plain(d) for d in docs]
    runs = [r for r in runs if r is not None]
    now = datetime.now(timezone.utc)
    runs = [r for r in (_normalize_active_run(db, r, now) for r in runs) if r is not None]
    return {"runs": runs, "count": len(runs)}


@router.get("/runs/{run_id}", dependencies=[Depends(verify_token)])
async def get_run(run_id: str) -> Dict[str, Any]:
    """Get details of a specific run from Firestore."""
    db = firestore_helpers._get_fs()
    doc = db.collection("pipeline_runs").document(run_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _derive_logical_duration(data)


@router.get("/runs/{run_id}/logs", dependencies=[Depends(verify_token)])
async def get_run_logs(run_id: str, since: int = 0, limit: int = 1000) -> Dict[str, Any]:
    """Return log entries for a run from the Firestore logs subcollection.

    Pass ``?since=N`` to return only entries after index N (incremental polling).
    Entries are sorted ascending by their timestamp sort key.
    """
    db = firestore_helpers._get_fs()
    logs_ref = db.collection("pipeline_runs").document(run_id).collection("logs")
    limit = max(1, min(limit, 5000))
    entries = [firestore_helpers._doc_to_plain(d) for d in logs_ref.stream()]
    entries = [e for e in entries if e is not None]
    entries.sort(key=_log_sort_key)
    sliced = entries[since : since + limit] if since < len(entries) else []
    return {"logs": sliced, "total": len(entries)}


@router.delete("/runs", dependencies=[Depends(verify_token)])
async def prune_runs() -> Dict[str, Any]:
    """Prune all terminal runs (completed, failed, cancelled, continued) from Firestore."""
    db = firestore_helpers._get_fs()
    terminal_statuses = ["completed", "failed", "cancelled", "continued"]
    runs_ref = db.collection("pipeline_runs")
    docs = list(runs_ref.where("status", "in", terminal_statuses).limit(500).stream())

    batch = db.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count % 500 == 0:
            batch.commit()
            batch = db.batch()
    if count % 500 != 0:
        batch.commit()

    return {"message": f"Pruned {count} finished runs", "count": count}


@router.delete("/runs/{run_id}", dependencies=[Depends(verify_token)])
async def cancel_or_delete_run(run_id: str) -> Dict[str, Any]:
    """Cancel an active run or delete a finished one from Firestore."""
    db = firestore_helpers._get_fs()
    doc_ref = db.collection("pipeline_runs").document(run_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Run not found")
    data = doc.to_dict() or {}
    status = data.get("status", "")
    if status in ("pending", "running"):
        doc_ref.update({"status": "cancelled"})
        for queue_doc in db.collection("pipeline_queue").where("run_id", "==", run_id).limit(20).stream():
            queue_data = queue_doc.to_dict() or {}
            if queue_data.get("status") in ("pending", "running"):
                queue_doc.reference.update({"status": "cancelled", "lease_owner": None, "lease_expires_at": None})
        race_id = data.get("race_id")
        if race_id:
            race_doc = db.collection("races").document(str(race_id)).get()
            race_data = firestore_helpers._doc_to_plain(race_doc) or {}
            if race_data.get("status") in ("queued", "running") and race_data.get("current_run_id") == run_id:
                firestore_helpers._fs_update_race(race_id, {"status": "cancelled", "current_run_id": None})
        return {"message": "Run cancelled", "run_id": run_id}
    else:
        doc_ref.delete()
    return {"message": "Run deleted", "run_id": run_id}
