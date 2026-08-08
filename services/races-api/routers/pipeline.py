"""Pipeline and infrastructure cost metrics endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import firestore_helpers
import gcp_costs
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException

from shared.config import FIRESTORE_METRICS_COLLECTION, FIRESTORE_RUNS_COLLECTION

router = APIRouter()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_pipeline_run(raw: Dict[str, Any], fallback_run_id: str) -> Dict[str, Any]:
    """Project heterogeneous pipeline_runs docs into a stable dashboard schema."""
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    options = raw.get("options") if isinstance(raw.get("options"), dict) else {}
    if isinstance(raw.get("agent_metrics"), dict):
        agent_metrics = raw["agent_metrics"]
    elif isinstance(payload.get("agent_metrics"), dict):
        agent_metrics = payload["agent_metrics"]
    else:
        agent_metrics = {}

    race_id = raw.get("race_id") or payload.get("race_id") or ""
    run_id = raw.get("run_id") or fallback_run_id
    status = raw.get("status") or "unknown"
    timestamp = raw.get("timestamp") or raw.get("started_at") or raw.get("completed_at")

    cheap_mode = raw.get("cheap_mode")
    if cheap_mode is None:
        cheap_mode = options.get("cheap_mode")

    model_breakdown = raw.get("model_breakdown")
    if not isinstance(model_breakdown, dict):
        model_breakdown = agent_metrics.get("model_breakdown")
    if not isinstance(model_breakdown, dict):
        model_breakdown = {}

    model = (
        raw.get("model")
        or agent_metrics.get("model")
        or options.get("research_model")
        or options.get("claude_model")
        or options.get("gemini_model")
        or options.get("grok_model")
        or ""
    )

    total_tokens = _as_int(raw.get("total_tokens"), _as_int(agent_metrics.get("total_tokens"), 0))
    prompt_tokens = _as_int(raw.get("prompt_tokens"), _as_int(agent_metrics.get("prompt_tokens"), 0))
    completion_tokens = _as_int(raw.get("completion_tokens"), _as_int(agent_metrics.get("completion_tokens"), 0))
    serper_calls = _as_int(raw.get("serper_calls"), _as_int(agent_metrics.get("serper_calls"), 0))
    searlo_calls = _as_int(raw.get("searlo_calls"), _as_int(agent_metrics.get("searlo_calls"), 0))

    estimated_usd = _as_float(
        raw.get("estimated_usd"),
        _as_float(raw.get("cost_usd"), _as_float(agent_metrics.get("estimated_usd"), 0.0)),
    )
    raw_cost_usd = raw.get("cost_usd")
    if raw_cost_usd is None:
        raw_cost_usd = agent_metrics.get("cost_usd")
    cost_usd = _as_float(raw_cost_usd) if raw_cost_usd is not None else None
    raw_llm_cost_usd = raw.get("llm_cost_usd")
    if raw_llm_cost_usd is None:
        raw_llm_cost_usd = agent_metrics.get("llm_cost_usd")
    llm_cost_usd = _as_float(raw_llm_cost_usd) if raw_llm_cost_usd is not None else None
    search_cost_usd = _as_float(
        raw.get("search_cost_usd"),
        _as_float(agent_metrics.get("search_cost_usd"), serper_calls * 0.001),
    )
    cost_source = raw.get("cost_source") or agent_metrics.get("cost_source")
    if cost_source not in {"provider", "estimated"}:
        cost_source = "provider" if cost_usd is not None else "estimated"

    candidate_count = _as_int(raw.get("candidate_count"), 0)
    if candidate_count <= 0 and isinstance(payload.get("candidates"), list):
        candidate_count = len(payload.get("candidates") or [])

    duration_s = _as_float(raw.get("logical_duration_ms"), 0.0) / 1000.0
    if duration_s <= 0:
        duration_s = _as_float(raw.get("duration_s"), 0.0)
    if duration_s <= 0:
        duration_ms = _as_float(raw.get("duration_ms"), 0.0)
        if duration_ms > 0:
            duration_s = round(duration_ms / 1000.0, 2)

    return {
        "run_id": run_id,
        "race_id": race_id,
        "status": status,
        "timestamp": timestamp,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_usd": round(estimated_usd, 6),
        "llm_cost_usd": llm_cost_usd,
        "search_cost_usd": search_cost_usd,
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        "model_breakdown": model_breakdown,
        "duration_s": duration_s,
        "segment_duration_s": _as_float(
            raw.get("segment_duration_s"),
            _as_float(agent_metrics.get("segment_duration_s"), 0.0),
        ),
        "continuation_count": _as_int(raw.get("continuation_count"), 0),
        "candidate_count": candidate_count,
        "cheap_mode": cheap_mode,
        "serper_calls": serper_calls,
        "searlo_calls": searlo_calls,
        "search_calls": _as_int(
            raw.get("search_calls"), _as_int(agent_metrics.get("search_calls"), serper_calls + searlo_calls)
        ),
        "search_budget_blocked": _as_int(
            raw.get("search_budget_blocked"),
            _as_int(agent_metrics.get("search_budget_blocked"), 0),
        ),
        "token_budget_nudges": _as_int(
            raw.get("token_budget_nudges"),
            _as_int(agent_metrics.get("token_budget_nudges"), 0),
        ),
        "model_profile": options.get("model_profile"),
    }


def _to_epoch_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return 0.0
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _has_pipeline_cost_data(raw: Dict[str, Any]) -> bool:
    """Return whether a heterogeneous run document carries usable cost data."""
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    agent_metrics = raw.get("agent_metrics")
    if not isinstance(agent_metrics, dict):
        agent_metrics = payload.get("agent_metrics")
    if not isinstance(agent_metrics, dict):
        agent_metrics = {}
    return any(
        value is not None
        for value in (
            raw.get("cost_usd"),
            raw.get("estimated_usd"),
            raw.get("llm_cost_usd"),
            agent_metrics.get("cost_usd"),
            agent_metrics.get("estimated_usd"),
            agent_metrics.get("llm_cost_usd"),
        )
    )


def _compute_metrics_summary(records: list[Dict[str, Any]]) -> Dict[str, Any]:
    total_runs = len(records)
    successful_runs = 0
    total_usd = 0.0
    recent_usd = 0.0
    cheap_runs = 0
    cheap_total_usd = 0.0
    full_runs = 0
    full_total_usd = 0.0
    candidate_count_runs = 0
    total_candidate_count = 0

    cutoff = datetime.now(timezone.utc).timestamp() - 30 * 86400
    for rec in records:
        if rec.get("status") == "completed":
            successful_runs += 1

        cost = _as_float(rec.get("cost_usd"), _as_float(rec.get("estimated_usd"), 0.0))
        total_usd += cost

        ts = _to_epoch_seconds(rec.get("timestamp"))
        if ts > cutoff:
            recent_usd += cost

        if rec.get("cheap_mode") is True:
            cheap_runs += 1
            cheap_total_usd += cost
        elif rec.get("cheap_mode") is False:
            full_runs += 1
            full_total_usd += cost

        candidate_count = _as_int(rec.get("candidate_count"), 0)
        if candidate_count > 0:
            candidate_count_runs += 1
            total_candidate_count += candidate_count

    avg_usd = total_usd / total_runs if total_runs > 0 else 0.0
    success_rate = successful_runs / total_runs if total_runs > 0 else 0.0
    avg_cheap_usd = cheap_total_usd / cheap_runs if cheap_runs > 0 else 0.0
    avg_full_usd = full_total_usd / full_runs if full_runs > 0 else 0.0
    avg_usd_per_candidate = total_usd / total_candidate_count if total_candidate_count > 0 else 0.0

    return {
        "total_runs": total_runs,
        "total_usd": round(total_usd, 4),
        "avg_usd": round(avg_usd, 4),
        "recent_30d_usd": round(recent_usd, 4),
        "success_rate": round(success_rate, 4),
        "cheap_runs": cheap_runs,
        "avg_cheap_usd": round(avg_cheap_usd, 4),
        "full_runs": full_runs,
        "avg_full_usd": round(avg_full_usd, 4),
        "avg_usd_per_candidate": round(avg_usd_per_candidate, 6),
        "runs_with_candidate_count": candidate_count_runs,
    }


# ---------------------------------------------------------------------------
# Pipeline metrics (token usage / cost)
# ---------------------------------------------------------------------------


@router.get("/pipeline/metrics", dependencies=[Depends(verify_token)])
async def get_pipeline_metrics(limit: int = 50) -> Dict[str, Any]:
    """Return recent pipeline run records with token usage and cost data."""
    limit = max(1, min(limit, 500))
    try:
        db = firestore_helpers._get_fs()
    except Exception as exc:
        logging.warning("Firestore unavailable for pipeline metrics: %s", exc)
        from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

        store = get_pipeline_metrics_store()
        if store._client is None:
            records = await store.get_recent(limit=limit)
            return {"records": records, "count": len(records)}
        raise HTTPException(status_code=503, detail="Pipeline metrics storage is temporarily unavailable") from exc
    metric_records: Dict[str, Dict[str, Any]] = {}
    run_records: Dict[str, Dict[str, Any]] = {}
    metric_query_ok = False
    run_query_ok = False

    # Primary source: pipeline_metrics (includes tokens/cost/model fields).
    try:
        docs = db.collection(FIRESTORE_METRICS_COLLECTION).order_by("timestamp", direction="DESCENDING").limit(limit).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None:
                continue
            record = _normalize_pipeline_run(plain, doc.id)
            metric_records[str(record["run_id"])] = record
        metric_query_ok = True
    except Exception as exc:
        logging.warning("Failed to load pipeline_metrics: %s", exc)

    # Recent runs are the dashboard row source; merge in metrics by run_id so a
    # populated but stale metrics collection does not make current rows look free.
    try:
        for timestamp_field in ("progress_updated_at", "completed_at", "updated_at", "started_at"):
            docs = (
                db.collection(FIRESTORE_RUNS_COLLECTION)
                .order_by(timestamp_field, direction="DESCENDING")
                .limit(limit)
                .stream()
            )
            for doc in docs:
                plain = firestore_helpers._doc_to_plain(doc)
                if plain is None:
                    continue
                record = _normalize_pipeline_run(plain, doc.id)
                run_records[str(record["run_id"])] = record
        run_query_ok = True
    except Exception as exc:
        logging.warning("Failed to load pipeline_runs for metrics merge: %s", exc)

    if not metric_query_ok and not run_query_ok:
        from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

        store = get_pipeline_metrics_store()
        if store._client is None:
            records = await store.get_recent(limit=limit)
            return {"records": records, "count": len(records)}
        raise HTTPException(status_code=503, detail="Pipeline metrics storage is temporarily unavailable")

    records: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for run_id, run_record in sorted(
        run_records.items(),
        key=lambda item: _to_epoch_seconds(item[1].get("timestamp")),
        reverse=True,
    ):
        merged = {**run_record, **metric_records.get(run_id, {})}
        if run_record.get("serper_calls") and not merged.get("serper_calls"):
            merged["serper_calls"] = run_record["serper_calls"]
        if run_record.get("duration_s") and not merged.get("duration_s"):
            merged["duration_s"] = run_record["duration_s"]
        for field in ("continuation_count", "search_budget_blocked", "token_budget_nudges"):
            if run_record.get(field) and not merged.get(field):
                merged[field] = run_record[field]
        records.append(merged)
        seen.add(run_id)

    for run_id, metric_record in sorted(
        metric_records.items(),
        key=lambda item: _to_epoch_seconds(item[1].get("timestamp")),
        reverse=True,
    ):
        if run_id in seen:
            continue
        records.append(metric_record)
        if len(records) >= limit:
            break

    return {"records": records[:limit], "count": min(len(records), limit)}


@router.get("/pipeline/metrics/summary", dependencies=[Depends(verify_token)])
async def get_pipeline_metrics_summary(hours: Optional[int] = None) -> Dict[str, Any]:
    """Return aggregate pipeline cost stats."""
    try:
        db = firestore_helpers._get_fs()
    except Exception as exc:
        logging.warning("Firestore unavailable for pipeline metrics summary: %s", exc)
        from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

        store = get_pipeline_metrics_store()
        if store._client is None:
            return await store.get_summary()
        raise HTTPException(status_code=503, detail="Pipeline metrics storage is temporarily unavailable") from exc
    metric_records: Dict[str, Dict[str, Any]] = {}
    run_records: Dict[str, Dict[str, Any]] = {}
    metric_query_ok = False
    run_query_ok = False
    try:
        docs = db.collection(FIRESTORE_METRICS_COLLECTION).order_by("timestamp", direction="DESCENDING").limit(5000).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None:
                continue
            record = _normalize_pipeline_run(plain, doc.id)
            metric_records[str(record["run_id"])] = record
        metric_query_ok = True
    except Exception as exc:
        logging.warning("Failed to summarize pipeline_metrics: %s", exc)

    try:
        docs = db.collection(FIRESTORE_RUNS_COLLECTION).limit(5000).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None or not _has_pipeline_cost_data(plain):
                continue
            record = _normalize_pipeline_run(plain, doc.id)
            run_records[str(record["run_id"])] = record
        run_query_ok = True
    except Exception as exc:
        logging.warning("Failed to summarize pipeline_runs: %s", exc)

    if not metric_query_ok and not run_query_ok:
        from pipeline_client.backend.pipeline_metrics import get_pipeline_metrics_store

        store = get_pipeline_metrics_store()
        if store._client is not None:
            raise HTTPException(status_code=503, detail="Pipeline metrics storage is temporarily unavailable")
        if hours is None or hours <= 0:
            return await store.get_summary()
        records = await store.get_recent(limit=5000)
    else:
        records = []
        for run_id in set(run_records) | set(metric_records):
            records.append({**run_records.get(run_id, {}), **metric_records.get(run_id, {})})

    if hours is not None and hours > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        records = [record for record in records if _to_epoch_seconds(record.get("timestamp")) >= cutoff]

    return _compute_metrics_summary(records)


# ---------------------------------------------------------------------------
# GCP infrastructure costs (Cloud Billing BigQuery export)
# ---------------------------------------------------------------------------


@router.get("/pipeline/gcp-costs", dependencies=[Depends(verify_token)])
async def get_gcp_costs(days: int = 30) -> Dict[str, Any]:
    """Return GCP spend by service from the Cloud Billing export.

    Degrades gracefully to ``{"configured": false, ...}`` when the billing
    export is not yet set up or has produced no data.
    """
    return gcp_costs.get_gcp_costs(days)
