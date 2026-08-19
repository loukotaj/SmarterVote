"""2026 research coverage, result checkpoints, and canonical status endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import firestore_helpers
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException
from request_models import ResearchCheckpointRequest, validate_race_id

from shared.config import FIRESTORE_RACES_COLLECTION, FIRESTORE_RESEARCH_CHECKPOINTS_COLLECTION
from shared.research_manifest import (
    excluded_race_reason,
    get_research_manifest_entry,
    list_research_manifest_entries,
    load_research_manifest,
)

router = APIRouter()
logger = logging.getLogger("races_api")


def _plain_checkpoint(db: Any, race_id: str) -> Dict[str, Any] | None:
    doc = db.collection(FIRESTORE_RESEARCH_CHECKPOINTS_COLLECTION).document(race_id).get()
    return firestore_helpers._doc_to_plain(doc)


def _active_override(checkpoint: Dict[str, Any] | None) -> Dict[str, Any] | None:
    override = checkpoint.get("coverage_override") if isinstance(checkpoint, dict) else None
    if not isinstance(override, dict) or override.get("active") is not True:
        return None
    if not str(override.get("official_source_url") or "").startswith(("https://", "http://")):
        return None
    if not str(override.get("reason") or "").strip() or not str(override.get("approved_by") or "").strip():
        return None
    return override


def assert_race_admitted(db: Any, race_id: str, operation: str) -> Dict[str, Any]:
    """Require manifest membership or a sourced override before race writes."""
    entry = get_research_manifest_entry(race_id)
    if entry is not None:
        return {"source": "manifest", "entry": entry}
    excluded_reason = excluded_race_reason(race_id)
    if excluded_reason:
        raise HTTPException(status_code=409, detail=f"Race is excluded from 2026 coverage: {excluded_reason}")
    checkpoint = _plain_checkpoint(db, race_id)
    override = _active_override(checkpoint)
    if override is not None:
        return {"source": "coverage_override", "entry": override}
    raise HTTPException(
        status_code=409,
        detail=(
            f"Race is not admitted for {operation}. Add it to the validated manifest or record a sourced, "
            "approved coverage override first."
        ),
    )


def _fingerprint(event_type: str | None, event_date: Any, advancing_names: list[str]) -> str | None:
    if not event_type or not event_date or not advancing_names:
        return None
    canonical = {
        "event_type": str(event_type).strip().casefold(),
        "event_date": str(event_date),
        "advancing_names": sorted(" ".join(name.split()).casefold() for name in advancing_names),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _artifact_view(catalog: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    exists = bool(catalog.get(f"{prefix}_updated_utc")) or bool(
        catalog.get("published_at" if prefix == "published" else "draft_updated_at")
    )
    health = catalog.get(f"{prefix}_catalog_health")
    return {
        "source": prefix,
        "exists": exists,
        "updated_utc": catalog.get(f"{prefix}_updated_utc"),
        "contest_stage": catalog.get(f"{prefix}_contest_stage") or "unknown",
        "candidate_count": catalog.get(f"{prefix}_candidate_count"),
        "quality_grade": catalog.get(f"{prefix}_quality_grade"),
        "health": health if isinstance(health, dict) else None,
    }


def _lifecycle(row: Dict[str, Any]) -> tuple[str, str]:
    checkpoint = row.get("checkpoint") or {}
    catalog = row.get("catalog") or {}
    result_state = checkpoint.get("result_state") or "waiting"
    if result_state in {"manual_review", "runoff_pending"}:
        return "manual_review", "manual_review"
    if result_state != "stable":
        return ("stabilizing" if result_state == "stabilizing" else "waiting_event"), "blocked_roster"
    if catalog.get("status") in {"queued", "running"}:
        return str(catalog["status"]), "blocked_roster"
    fingerprint = checkpoint.get("result_fingerprint")
    reviewed = checkpoint.get("last_reviewed_discovery_fingerprint")
    if not fingerprint or fingerprint != reviewed:
        latest = row.get("latest") or {}
        return ("review_required" if latest.get("exists") else "ready"), "blocked_roster"
    latest_health = (row.get("latest") or {}).get("health") or {}
    missing_issues = int(latest_health.get("missing_issue_count") or 0)
    return "complete", ("ready" if missing_issues else "complete")


def _cost_by_race(db: Any) -> tuple[Dict[str, Dict[str, Any]], Dict[str, float]]:
    """Join deduplicated run/metric records into workflow-aware spend totals."""
    from routers.pipeline import _load_summary_firestore_records, _merge_run_metric

    try:
        metric_records, run_records, _, _ = _load_summary_firestore_records(db)
    except Exception as exc:
        logger.warning("Research status could not load pipeline costs: %s", exc)
        return {}, {}

    by_race: Dict[str, Dict[str, Any]] = {}
    by_workflow: Dict[str, float] = {}
    for run_id in set(run_records) | set(metric_records):
        record = _merge_run_metric(run_records.get(run_id, {}), metric_records.get(run_id, {}))
        race_id = str(record.get("race_id") or "")
        if not race_id:
            continue
        workflow = str(record.get("workflow") or "unknown")
        raw_cost = record.get("cost_usd")
        cost = float(raw_cost if raw_cost is not None else record.get("estimated_usd") or 0.0)
        summary = by_race.setdefault(race_id, {"run_count": 0, "total_usd": 0.0, "by_workflow": {}, "last_run_at": None})
        summary["run_count"] += 1
        summary["total_usd"] += cost
        summary["by_workflow"][workflow] = summary["by_workflow"].get(workflow, 0.0) + cost
        timestamp = record.get("timestamp")
        if timestamp and (summary["last_run_at"] is None or str(timestamp) > str(summary["last_run_at"])):
            summary["last_run_at"] = timestamp
        by_workflow[workflow] = by_workflow.get(workflow, 0.0) + cost

    for summary in by_race.values():
        summary["total_usd"] = round(summary["total_usd"], 6)
        summary["by_workflow"] = {key: round(value, 6) for key, value in summary["by_workflow"].items()}
    return by_race, {key: round(value, 6) for key, value in by_workflow.items()}


@router.get("/api/research/manifest", dependencies=[Depends(verify_token)])
def get_research_manifest() -> Dict[str, Any]:
    manifest = load_research_manifest()
    return {
        "schema_version": manifest["schema_version"],
        "cycle": manifest["cycle"],
        "coverage_count": manifest["coverage_count"],
        "sources": manifest["sources"],
        "excluded_races": manifest["excluded_races"],
        "races": list_research_manifest_entries(),
    }


@router.get("/api/research/checkpoints/{race_id}", dependencies=[Depends(verify_token)])
def get_research_checkpoint(race_id: str) -> Dict[str, Any]:
    validate_race_id(race_id)
    checkpoint = _plain_checkpoint(firestore_helpers._get_fs(), race_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Research checkpoint not found")
    return checkpoint


@router.put("/api/research/checkpoints/{race_id}", dependencies=[Depends(verify_token)])
def record_research_checkpoint(race_id: str, payload: ResearchCheckpointRequest) -> Dict[str, Any]:
    validate_race_id(race_id)
    db = firestore_helpers._get_fs()
    existing = _plain_checkpoint(db, race_id)
    manifest_entry = get_research_manifest_entry(race_id)
    serialized = payload.model_dump(mode="json", exclude_none=True)
    excluded_reason = excluded_race_reason(race_id)
    if excluded_reason:
        raise HTTPException(status_code=409, detail=f"Race is excluded from 2026 coverage: {excluded_reason}")
    if manifest_entry is None and _active_override(serialized) is None:
        raise HTTPException(
            status_code=409,
            detail="Race is not in manifest; an active sourced coverage_override is required",
        )
    result_fingerprint = _fingerprint(payload.event_type, payload.event_date, payload.advancing_names)
    now = datetime.now(timezone.utc).isoformat()
    checkpoint = {
        **serialized,
        "race_id": race_id,
        "cycle": 2026,
        "manifest_entry": manifest_entry,
        "result_fingerprint": result_fingerprint,
        "updated_at": now,
    }
    if "coverage_override" not in checkpoint and _active_override(existing) is not None:
        checkpoint["coverage_override"] = existing["coverage_override"]
    db.collection(FIRESTORE_RESEARCH_CHECKPOINTS_COLLECTION).document(race_id).set(checkpoint)
    return checkpoint


@router.get("/api/research/status", dependencies=[Depends(verify_token)])
def get_research_program_status(include_rows: bool = True) -> Dict[str, Any]:
    # Lazy import avoids a package-initialization cycle: queue and draft routers
    # import the admission helper from this module.
    from routers.races_admin.helpers import _apply_catalog_view

    db = firestore_helpers._get_fs()
    catalog_docs = db.collection(FIRESTORE_RACES_COLLECTION).limit(10000).stream()
    catalogs: Dict[str, Dict[str, Any]] = {}
    for doc in catalog_docs:
        plain = firestore_helpers._doc_to_plain(doc)
        if plain is None:
            continue
        race_id = str(plain.get("race_id") or plain.get("id") or doc.id)
        plain["race_id"] = race_id
        catalogs[race_id] = _apply_catalog_view(plain)

    checkpoint_docs = db.collection(FIRESTORE_RESEARCH_CHECKPOINTS_COLLECTION).limit(10000).stream()
    checkpoints: Dict[str, Dict[str, Any]] = {}
    for doc in checkpoint_docs:
        plain = firestore_helpers._doc_to_plain(doc)
        if plain is not None:
            checkpoints[str(plain.get("race_id") or doc.id)] = plain

    race_costs, workflow_spend = _cost_by_race(db)

    rows = []
    for entry in list_research_manifest_entries():
        race_id = entry["race_id"]
        catalog = catalogs.get(race_id, {})
        published = _artifact_view(catalog, "published")
        draft = _artifact_view(catalog, "draft")
        latest = draft if draft["exists"] else published
        row = {
            "race_id": race_id,
            "manifest": entry,
            "checkpoint": checkpoints.get(race_id),
            "catalog": {
                "source": "catalog",
                "status": catalog.get("status"),
                "current_run_id": catalog.get("current_run_id"),
                "last_run_status": catalog.get("last_run_status"),
            },
            "published": published,
            "draft": draft,
            "latest": latest,
            "latest_source": latest["source"],
            "cost": race_costs.get(race_id, {"run_count": 0, "total_usd": 0.0, "by_workflow": {}, "last_run_at": None}),
        }
        discovery_state, issue_state = _lifecycle(row)
        row["discovery_state"] = discovery_state
        row["issue_state"] = issue_state
        rows.append(row)

    manifest_ids = {row["race_id"] for row in rows}
    overrides = {race_id for race_id, checkpoint in checkpoints.items() if _active_override(checkpoint)}
    orphaned = sorted(race_id for race_id in catalogs if race_id not in manifest_ids and race_id not in overrides)
    result_states: Dict[str, int] = {}
    discovery_states: Dict[str, int] = {}
    issue_states: Dict[str, int] = {}
    for row in rows:
        result_state = str((row.get("checkpoint") or {}).get("result_state") or "waiting")
        result_states[result_state] = result_states.get(result_state, 0) + 1
        discovery_states[row["discovery_state"]] = discovery_states.get(row["discovery_state"], 0) + 1
        issue_states[row["issue_state"]] = issue_states.get(row["issue_state"], 0) + 1
    return {
        "rows": rows if include_rows else [],
        "summary": {
            "coverage_count": len(rows),
            "catalog_present_count": sum(bool(row["published"]["exists"] or row["draft"]["exists"]) for row in rows),
            "checkpoint_count": sum(bool(row.get("checkpoint")) for row in rows),
            "orphaned_catalog_count": len(orphaned),
            "result_states": result_states,
            "discovery_states": discovery_states,
            "issue_states": issue_states,
            "workflow_spend_usd": workflow_spend,
            "total_pipeline_spend_usd": round(sum(workflow_spend.values()), 6),
        },
        "orphaned_catalog_race_ids": orphaned,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
