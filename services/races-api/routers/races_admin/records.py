"""Race record (Firestore metadata) CRUD, status reconciliation, and run trigger endpoints."""

import asyncio
import ipaddress
import logging
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse

import firestore_helpers
import gcs_helpers
import httpx
from auth import verify_token
from cloud_run_jobs import dispatch_pipeline_job
from fastapi import APIRouter, Depends, HTTPException, Request
from request_models import AssetAuditRequest, RepairPlanRequest, RunOptions, validate_race_id
from routers.utils import _queue_ttl_at

from shared.config import FIRESTORE_QUEUE_COLLECTION, FIRESTORE_RACES_COLLECTION, FIRESTORE_RUNS_COLLECTION
from shared.repair_planner import build_repair_plan, summarize_repair_plans

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
def list_all_races() -> Dict[str, Any]:
    """List all race records from Firestore (admin view with catalog metadata)."""
    db = firestore_helpers._get_fs()
    docs = db.collection(FIRESTORE_RACES_COLLECTION).limit(10000).stream()
    races = []
    for d in docs:
        plain = firestore_helpers._doc_to_plain(d)
        if plain is not None:
            if not plain.get("race_id"):
                plain["race_id"] = d.id
            races.append(plain)

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
def list_draft_races() -> Dict[str, Any]:
    """List all draft race summaries from the Firestore race catalog."""
    db = firestore_helpers._get_fs()
    docs = db.collection(FIRESTORE_RACES_COLLECTION).limit(1000).stream()
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
def recheck_all_race_statuses(cursor: str | None = None, limit: int = 50) -> Dict[str, Any]:
    """Reconcile one bounded catalog page and return an opaque continuation cursor."""
    db = firestore_helpers._get_fs()
    docs = db.collection(FIRESTORE_RACES_COLLECTION).limit(10000).stream()
    races: list[Dict[str, Any]] = []
    updated = 0
    docs_by_race_id: dict[str, Any] = {}
    for doc in docs:
        race_data = firestore_helpers._doc_to_plain(doc)
        if not race_data:
            continue
        race_id = str(race_data.get("race_id") or race_data.get("id") or doc.id)
        if not race_data.get("race_id"):
            race_data["race_id"] = race_id
        docs_by_race_id[race_id] = race_data

    storage_ids = set(gcs_helpers._gcs_list_race_ids("races") or [])
    storage_ids.update(gcs_helpers._gcs_list_race_ids("drafts") or [])
    all_race_ids = sorted(set(docs_by_race_id) | {str(race_id) for race_id in storage_ids})
    if cursor:
        all_race_ids = [race_id for race_id in all_race_ids if race_id > cursor]
    limit = max(1, min(int(limit), 200))
    page_ids = all_race_ids[:limit]

    for race_id in page_ids:
        race_data = docs_by_race_id.get(race_id)
        if race_data is not None:
            latest, changed = _recheck_race_status(db, race_id, race_data)
            if latest:
                races.append(latest)
            updated += int(changed)
            continue
        update = _backfill_catalog_from_storage(race_id)
        if update is not None:
            races.append({"race_id": race_id, **update})
            updated += 1

    has_more = len(all_race_ids) > len(page_ids)
    next_cursor = page_ids[-1] if has_more and page_ids else None
    return {
        "message": f"Rechecked {len(races)} races",
        "checked": len(races),
        "updated": updated,
        "races": races,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.post("/api/races/repair-plan", dependencies=[Depends(verify_token)])
def plan_race_repairs(request: RepairPlanRequest) -> Dict[str, Any]:
    """Build bounded repair plans from the latest draft-or-published RaceJSON."""
    db = firestore_helpers._get_fs()
    plans = []
    missing_race_ids = []
    for race_id in request.race_ids:
        catalog_doc = db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).get()
        catalog = firestore_helpers._doc_to_plain(catalog_doc) or {}
        _apply_catalog_view(catalog)
        race_data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
        if not isinstance(race_data, dict):
            race_data = gcs_helpers._gcs_get_race_json(race_id, "races")
        if not isinstance(race_data, dict):
            missing_race_ids.append(race_id)
            continue
        plans.append(build_repair_plan(race_id, race_data, freshness=catalog.get("freshness")))
    return {**summarize_repair_plans(plans), "missing_race_ids": missing_race_ids}


def _asset_urls(race_data: Dict[str, Any]) -> list[tuple[str, str]]:
    assets: list[tuple[str, str]] = []
    for candidate in race_data.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("image_url"):
            assets.append(("image", str(candidate["image_url"])))
        for key in ("roster_sources", "donor_sources", "voting_sources", "summary_sources"):
            for source in candidate.get(key) or []:
                if isinstance(source, dict) and source.get("url"):
                    assets.append((key, str(source["url"])))
        for issue in (candidate.get("issues") or {}).values():
            if isinstance(issue, dict):
                for source in issue.get("sources") or []:
                    if isinstance(source, dict) and source.get("url"):
                        assets.append(("issue_source", str(source["url"])))
    forecast = race_data.get("forecast") or {}
    for url in forecast.get("source_urls") or []:
        assets.append(("forecast_source", str(url)))
    return list(dict.fromkeys(assets))


def _safe_public_asset_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.casefold()
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


async def _host_resolves_public(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    resolved = {entry[4][0] for entry in addresses}
    return bool(resolved) and all(ipaddress.ip_address(address).is_global for address in resolved)


async def _probe_asset(client: httpx.AsyncClient, kind: str, url: str) -> Dict[str, Any]:
    if not _safe_public_asset_url(url) or not await _host_resolves_public(url):
        return {"kind": kind, "url": url, "status": "blocked", "reachable": False}
    try:
        response = await client.head(url, follow_redirects=False)
        content_type = response.headers.get("content-type", "").split(";")[0].lower()
        reachable = response.status_code < 400 or response.status_code in {401, 403, 405, 429}
        image_valid = (
            None
            if kind != "image" or response.status_code in {401, 403, 405, 429} or not content_type
            else content_type.startswith("image/")
        )
        content_length = int(response.headers.get("content-length") or 0) or None
        thumbnail_match = re.search(r"(?:^|[-_/])(\d{2,4})x(\d{2,4})(?:[-_.?/]|$)", url, re.IGNORECASE)
        suspicious_thumbnail = bool(
            thumbnail_match and min(int(thumbnail_match.group(1)), int(thumbnail_match.group(2))) < 150
        )
        image_quality = None
        if kind == "image" and image_valid is False:
            image_quality = "invalid_content_type"
        elif (
            kind == "image"
            and image_valid is True
            and (suspicious_thumbnail or (content_length is not None and content_length < 10_000))
        ):
            image_quality = "suspicious_small"
        elif kind == "image" and image_valid is True:
            image_quality = "content_type_valid"
        return {
            "kind": kind,
            "url": url,
            "status": "rate_limited" if response.status_code == 429 else "reachable" if reachable else "broken",
            "reachable": reachable,
            "http_status": response.status_code,
            "content_type": content_type or None,
            "content_length": content_length,
            "image_content_type_valid": image_valid,
            "image_quality": image_quality,
            "redirect_location": response.headers.get("location"),
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"kind": kind, "url": url, "status": "error", "reachable": False, "error": str(exc)[:300]}


@router.post("/api/races/asset-audit", dependencies=[Depends(verify_token)])
async def audit_race_assets(request: AssetAuditRequest) -> Dict[str, Any]:
    """Probe bounded race assets without downloading their bodies; optionally persist results."""
    db = firestore_helpers._get_fs()
    audited_at = datetime.now(timezone.utc).isoformat()
    results = []
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "SmarterVote asset auditor/1.0"}) as client:
        for race_id in request.race_ids:
            race_data = gcs_helpers._gcs_get_race_json(race_id, "drafts")
            if not isinstance(race_data, dict):
                race_data = gcs_helpers._gcs_get_race_json(race_id, "races")
            if not isinstance(race_data, dict):
                results.append({"race_id": race_id, "missing": True})
                continue
            assets = _asset_urls(race_data)[: request.max_urls_per_race]
            probes = await asyncio.gather(*(_probe_asset(client, kind, url) for kind, url in assets))
            result = {
                "race_id": race_id,
                "audited_at": audited_at,
                "asset_count": len(probes),
                "reachable_count": sum(bool(probe.get("reachable")) for probe in probes),
                "broken_count": sum(not bool(probe.get("reachable")) for probe in probes),
                "invalid_image_count": sum(probe.get("image_content_type_valid") is False for probe in probes),
                "suspicious_image_count": sum(probe.get("image_quality") == "suspicious_small" for probe in probes),
                "assets": probes,
            }
            results.append(result)
            if request.persist:
                db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).set(
                    {"asset_audit": result, "asset_audited_at": audited_at},
                    merge=True,
                )
    return {"results": results, "persisted": request.persist}


@router.get("/api/races/{race_id}", dependencies=[Depends(verify_token)])
def get_race_record(race_id: str) -> Dict[str, Any]:
    """Get a single race record from Firestore."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    doc = db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).get()
    data = firestore_helpers._doc_to_plain(doc)
    if data is None:
        raise HTTPException(status_code=404, detail="Race not found")
    if not data.get("race_id"):
        data["race_id"] = race_id
    _apply_catalog_view(data)
    return data


@router.delete("/api/races/{race_id}", dependencies=[Depends(verify_token)])
def delete_race_record(request: Request, race_id: str) -> Dict[str, Any]:
    """Delete a race record and all associated GCS blobs."""
    validate_race_id(race_id)
    gcs_helpers._gcs_delete_race_json(race_id, "races")
    gcs_helpers._gcs_delete_race_json(race_id, "drafts")
    gcs_helpers.update_gcs_summaries_json({race_id: None})
    try:
        firestore_helpers._get_fs().collection(FIRESTORE_RACES_COLLECTION).document(race_id).delete()
    except Exception as exc:
        logging.warning("Firestore delete race %s failed: %s", race_id, exc)
    _clear_public_race_cache(request)
    return {"message": f"Race {race_id} deleted", "id": race_id}


@router.post("/api/races/{race_id}/cancel", dependencies=[Depends(verify_token)])
def cancel_race(race_id: str) -> Dict[str, Any]:
    """Cancel a queued or running race by updating Firestore state."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    race_doc = db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).get()
    if not race_doc.exists:
        raise HTTPException(status_code=404, detail="Race not found")
    race_data = race_doc.to_dict() or {}
    if race_data.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=400, detail="Race is not queued or running")
    for doc in db.collection(FIRESTORE_QUEUE_COLLECTION).where("race_id", "==", race_id).stream():
        d = doc.to_dict() or {}
        if d.get("status") in ("pending", "running"):
            doc.reference.update(
                {"status": "cancelled", "lease_owner": None, "lease_expires_at": None, "ttl_at": _queue_ttl_at()}
            )
    run_id = race_data.get("current_run_id")
    if run_id:
        run_ref = db.collection(FIRESTORE_RUNS_COLLECTION).document(run_id)
        run_doc = run_ref.get()
        if run_doc.exists and (run_doc.to_dict() or {}).get("status") in ("pending", "running"):
            run_ref.update({"status": "cancelled"})
    firestore_helpers._fs_update_race(race_id, {"status": "cancelled", "current_run_id": None})
    return {"message": f"Race {race_id} cancelled"}


@router.post("/api/races/{race_id}/recheck", dependencies=[Depends(verify_token)])
def recheck_race_status(race_id: str) -> Dict[str, Any]:
    """Re-derive race status from GCS storage state and backfill missing race docs."""
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    race_doc = db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).get()
    if not race_doc.exists:
        update = _backfill_catalog_from_storage(race_id)
        if update is None:
            raise HTTPException(status_code=404, detail="Race not found")
        return {"message": f"Race {race_id} rechecked", "race": {"race_id": race_id, **update}}
    race_data = race_doc.to_dict() or {}
    latest, _changed = _recheck_race_status(db, race_id, race_data)
    return {"message": f"Race {race_id} rechecked", "race": latest}


@router.post("/api/races/{race_id}/run", dependencies=[Depends(verify_token)])
def run_race_pipeline(race_id: str, options: RunOptions | None = None) -> Dict[str, Any]:
    """Trigger the pipeline for a race by writing to the Firestore queue."""
    validate_race_id(race_id)
    opts = options.model_dump(exclude_none=True) if options else {}
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP  # type: ignore

    db = firestore_helpers._get_fs()
    race_doc = db.collection(FIRESTORE_RACES_COLLECTION).document(race_id).get()
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
    db.collection(FIRESTORE_QUEUE_COLLECTION).document(item_id).set(item)
    firestore_helpers._fs_update_race(race_id, {"status": "queued", "current_run_id": run_id})
    dispatch = None
    if item["runner"] == "cloud_run":
        try:
            dispatch = dispatch_pipeline_job(item_id)
            db.collection(FIRESTORE_QUEUE_COLLECTION).document(item_id).update({"dispatch_status": "submitted", **dispatch})
        except Exception as exc:
            error = f"Cloud Run Job dispatch failed: {exc}"
            db.collection(FIRESTORE_QUEUE_COLLECTION).document(item_id).update(
                {"status": "failed", "dispatch_status": "failed", "error": error, "ttl_at": _queue_ttl_at()}
            )
            firestore_helpers._fs_update_race(
                race_id, {"status": "failed", "current_run_id": None, "last_run_status": "failed"}
            )
            raise HTTPException(status_code=503, detail=error) from exc
    return {"run_id": run_id, "status": "queued", "race_id": race_id, "runner": item["runner"], "dispatch": dispatch}
