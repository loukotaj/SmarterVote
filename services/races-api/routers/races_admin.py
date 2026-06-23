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

from shared.pipeline_config import RetentionConfig
from shared.race_catalog import build_race_summary_fields

router = APIRouter()

STALE_ACTIVE_RUN_SECONDS = int(os.getenv("STALE_ACTIVE_RUN_SECONDS", "7200"))
_RETENTION = RetentionConfig.from_env()


def _queue_ttl_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=_RETENTION.completed_queue_days)


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
                if run_actually_active:
                    queue_docs = db.collection("pipeline_queue").where("run_id", "==", run_id).stream()
                    active_queue_docs = [doc for doc in queue_docs if _active_doc_is_fresh(doc.to_dict() or {}, now)]
                    run_actually_active = bool(active_queue_docs)
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


# ---------------------------------------------------------------------------
# Race records (Firestore metadata)
# ---------------------------------------------------------------------------


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


from pydantic import BaseModel, Field

DEFAULT_CHAMBER_FORECAST_MODEL = "google/gemini-3.5-flash"


class GenerateForecastsRequest(BaseModel):
    model: str = Field(default=DEFAULT_CHAMBER_FORECAST_MODEL)


@router.get("/api/races/chamber_forecasts/draft", dependencies=[Depends(verify_token)])
async def get_chamber_forecasts_draft_endpoint() -> Dict[str, Any]:
    """Retrieve overall chamber-level forecasts draft from GCS or local file."""
    data = gcs_helpers.load_chamber_forecasts(draft=True)
    if not data:
        raise HTTPException(status_code=404, detail="Chamber forecasts draft not found")
    return data


@router.post("/api/races/chamber_forecasts/generate", dependencies=[Depends(verify_token)])
async def generate_chamber_forecasts_endpoint(
    request: Request, payload: GenerateForecastsRequest = GenerateForecastsRequest()
) -> Dict[str, Any]:
    """Automatically generate chamber-level forecast narratives using an LLM and save them to drafts."""
    from pipeline_client.agent.chamber_narratives import generate_chamber_analyses
    from shared.forecast_summary import build_chamber_forecasts

    service = request.app.state.publish_service
    summaries = service.get_race_summaries()

    if not isinstance(summaries, list):
        raise HTTPException(status_code=500, detail=f"Invalid summaries from publish service: {type(summaries)}")

    try:
        analyses = await generate_chamber_analyses(summaries, model=payload.model)
    except Exception as exc:
        logging.error("Error generating chamber forecast analyses using model %s: %s", payload.model, exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"LLM chamber forecast generation failed: {exc}") from exc

    forecast_data = build_chamber_forecasts(
        summaries,
        {chamber: analysis["narrative"] for chamber, analysis in analyses.items()},
        analyses,
    )

    try:
        gcs_helpers.save_chamber_forecasts(forecast_data, draft=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save chamber forecasts draft: {exc}")

    return {
        "message": "Draft chamber forecasts generated successfully",
        "updated_at": forecast_data["updated_at"],
        "model": payload.model,
        "forecast": forecast_data,
    }


@router.post("/api/races/chamber_forecasts/publish", dependencies=[Depends(verify_token)])
async def publish_chamber_forecasts_endpoint(request: Request) -> Dict[str, Any]:
    """Publish the draft chamber-level forecasts (copy draft -> published in GCS)."""
    data = gcs_helpers.load_chamber_forecasts(draft=True)
    if not data:
        raise HTTPException(status_code=404, detail="Chamber forecasts draft not found")

    schema_version = data.get("schema_version")
    if schema_version != "chamber_forecasts.v2":
        raise HTTPException(status_code=400, detail=f"Expected schema_version chamber_forecasts.v2, got {schema_version}")

    chambers = data.get("chambers", {})
    expected_totals = {"house": 435, "senate": 100, "governors": 50}
    required_fields = [
        "seat_distribution",
        "bottom_line",
        "why_party_favored",
        "opposing_party_path",
        "key_uncertainty",
    ]
    for chamber_id, expected_total in expected_totals.items():
        chamber = chambers.get(chamber_id, {})
        if not chamber:
            raise HTTPException(status_code=400, detail=f"{chamber_id} chamber forecast missing")

        projected = chamber.get("projected_seats", {})
        total_projected = sum(projected.values())
        if total_projected != expected_total:
            raise HTTPException(
                status_code=400,
                detail=f"{chamber_id} projected seats must sum to {expected_total}, got {total_projected}",
            )

        for f in required_fields:
            if f not in chamber:
                raise HTTPException(status_code=400, detail=f"{chamber_id} chamber forecast missing required field: {f}")
        if not chamber.get("seat_distribution"):
            raise HTTPException(status_code=400, detail=f"{chamber_id} chamber forecast must include seat_distribution data")

    senate = chambers["senate"]
    if senate.get("vp_tiebreak_party") != "Republican":
        raise HTTPException(status_code=400, detail="Senate chamber forecast missing Republican VP tie-break assumption")
    projected = senate.get("projected_seats", {})
    if projected.get("Democratic") == 50 and projected.get("Republican") == 50:
        if senate.get("control_party") != "Republican":
            raise HTTPException(status_code=400, detail="Senate 50-50 projected split must result in Republican control")

    try:
        gcs_helpers.save_chamber_forecasts(data, draft=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to publish chamber forecasts: {exc}")

    # Clear memory cache on simple publish service
    service = request.app.state.publish_service
    if service:
        service.clear_cache()

    return {"message": "Chamber forecasts published successfully", "updated_at": data.get("updated_at")}


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
    update: Dict[str, Any] = {
        "status": "published" if has_published else "empty",
        "draft_updated_at": None,
        "draft_updated_utc": None,
        "draft_candidate_count": None,
        "draft_quality_grade": None,
    }
    if has_published:
        published_data = gcs_helpers._gcs_get_race_json(race_id, "races")
        if isinstance(published_data, dict):
            update.update(firestore_helpers._fs_build_published_catalog_fields(race_id, published_data))
    firestore_helpers._fs_update_race(race_id, update)
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
    gcs_helpers.update_gcs_summaries_json({race_id: data})
    firestore_helpers._fs_update_race(
        race_id,
        {
            **_published_race_update(),
            **firestore_helpers._fs_build_published_catalog_fields(race_id, data),
            "draft_updated_utc": None,
            "draft_candidate_count": None,
            "draft_quality_grade": None,
        },
    )
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
    gcs_helpers.update_gcs_summaries_json({race_id: None})
    update: Dict[str, Any] = {
        "status": "draft" if has_draft else "empty",
        "published_at": None,
        "published_updated_utc": None,
        "published_candidate_count": None,
        "published_quality_grade": None,
        "draft_updated_at": datetime.now(timezone.utc).isoformat() if has_draft else None,
    }
    if has_draft:
        draft_data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
        if isinstance(draft_data, dict):
            update.update(firestore_helpers._fs_build_draft_catalog_fields(race_id, draft_data))
    firestore_helpers._fs_update_race(race_id, update)
    _clear_public_race_cache(request)
    return {"message": f"Race {race_id} unpublished (draft retained)", "id": race_id}


@router.post("/api/races/publish", dependencies=[Depends(verify_token)])
async def batch_publish_races(request: Request, payload: BatchPublishRequest) -> Dict[str, Any]:
    """Publish multiple races at once (draft -> published)."""
    published = []
    errors = []
    updates_for_gcs = {}
    for race_id in payload.race_ids:
        try:
            validate_race_id(race_id)
            data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
            if data is None:
                errors.append({"race_id": race_id, "error": "Draft not found"})
                continue
            _assert_publishable_race(data)
            gcs_helpers._publish_race_gcs(race_id, data)
            updates_for_gcs[race_id] = data
            firestore_helpers._fs_update_race(
                race_id,
                {
                    **_published_race_update(),
                    **firestore_helpers._fs_build_published_catalog_fields(race_id, data),
                    "draft_updated_utc": None,
                    "draft_candidate_count": None,
                    "draft_quality_grade": None,
                },
            )
            published.append(race_id)
        except HTTPException as exc:
            errors.append({"race_id": race_id, "error": exc.detail})
        except Exception as exc:
            errors.append({"race_id": race_id, "error": str(exc)})
    if published:
        gcs_helpers.update_gcs_summaries_json(updates_for_gcs)
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
                    queue_doc.reference.update({"status": "cancelled", "ttl_at": _queue_ttl_at()})
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
        {
            "status": "draft",
            "published_at": None,
            "draft_updated_at": datetime.now(timezone.utc).isoformat(),
            **firestore_helpers._fs_build_draft_catalog_fields(race_id, version_data),
        },
    )
    return {"message": f"Retired version restored as draft for {race_id}", "id": race_id, "restored_from": filename}


# End of routes
