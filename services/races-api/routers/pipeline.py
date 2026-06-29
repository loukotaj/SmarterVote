"""Pipeline metrics, alerts, and admin-chat endpoints."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import firestore_helpers
import httpx
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException
from request_models import AdminChatRequest

router = APIRouter()

_ADMIN_CHAT_MODEL = os.getenv("ADMIN_CHAT_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")


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
    agent_metrics = payload.get("agent_metrics") if isinstance(payload.get("agent_metrics"), dict) else {}

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

    estimated_usd = _as_float(
        raw.get("estimated_usd"),
        _as_float(raw.get("cost_usd"), _as_float(agent_metrics.get("estimated_usd"), 0.0)),
    )
    raw_cost_usd = raw.get("cost_usd")
    if raw_cost_usd is None:
        raw_cost_usd = agent_metrics.get("cost_usd")
    cost_usd = _as_float(raw_cost_usd) if raw_cost_usd is not None else None
    cost_source = raw.get("cost_source") or agent_metrics.get("cost_source")
    if cost_source not in {"provider", "estimated"}:
        cost_source = "provider" if cost_usd is not None else "estimated"

    candidate_count = _as_int(raw.get("candidate_count"), 0)
    if candidate_count <= 0 and isinstance(payload.get("candidates"), list):
        candidate_count = len(payload.get("candidates") or [])

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
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        "model_breakdown": model_breakdown,
        "duration_s": duration_s,
        "candidate_count": candidate_count,
        "cheap_mode": cheap_mode,
        "serper_calls": serper_calls,
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


def _parse_admin_chat_reply(reply_text: str) -> Dict[str, Any]:
    """Parse optional control blocks from the admin-chat model response."""
    question = None
    action = None

    question_match = re.search(r"\nQUESTION:(\{[^\n]+\})\s*$", reply_text)
    if question_match:
        try:
            q_data = json.loads(question_match.group(1))
            question = q_data.get("text") or None
            reply_text = reply_text[: question_match.start()].rstrip()
        except (json.JSONDecodeError, ValueError):
            pass

    action_match = re.search(r"\nACTION:(\{[^\n]+\})\s*$", reply_text)
    if action_match:
        try:
            action = json.loads(action_match.group(1))
            reply_text = reply_text[: action_match.start()].rstrip()
            if isinstance(action, dict) and action.get("type") == "queue_run":
                options = action.setdefault("options", {})
                if isinstance(options, dict):
                    options.setdefault("cheap_mode", True)
        except (json.JSONDecodeError, ValueError):
            pass

    thinking_steps = []
    if action:
        thinking_steps.append(f"Prepared run for {len(action.get('race_ids') or [])} race(s)")
    if question:
        thinking_steps.append("Needs clarification before queuing")

    return {
        "reply": reply_text,
        "action": action,
        "race_records": [],
        "question": question,
        "thinking_steps": thinking_steps,
    }


def _compact_admin_race_context(records: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Keep only bounded, low-volume fields needed for admin chat grounding."""
    allowed = (
        "race_id",
        "id",
        "title",
        "status",
        "quality_grade",
        "freshness",
        "candidate_count",
        "last_run_at",
        "last_run_status",
        "published_at",
        "draft_updated_at",
        "office",
        "jurisdiction",
        "election_date",
    )
    compact: list[Dict[str, Any]] = []
    for record in records:
        item = {key: record.get(key) for key in allowed if record.get(key) is not None}
        if item:
            compact.append(item)
    return compact


def _load_admin_race_context(limit: int = 100) -> list[Dict[str, Any]]:
    """Load compact race records for admin-chat grounding."""
    try:
        docs = firestore_helpers._get_fs().collection("races").limit(limit).stream()
        records = [firestore_helpers._doc_to_plain(doc) for doc in docs]
        return _compact_admin_race_context([record for record in records if record is not None])
    except Exception as exc:
        logging.warning("Failed to load admin-chat race context: %s", exc)
        return []


def _race_records_for_action(action: Dict[str, Any] | None, context: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Return race records referenced by a queue_run action."""
    if not action or action.get("type") != "queue_run":
        return []
    ids = set(action.get("race_ids") or [])
    records = []
    for record in context:
        race_id = record.get("race_id") or record.get("id")
        if race_id in ids:
            records.append(record)
    return records


# ---------------------------------------------------------------------------
# Pipeline metrics (token usage / cost)
# ---------------------------------------------------------------------------


@router.get("/pipeline/metrics", dependencies=[Depends(verify_token)])
async def get_pipeline_metrics(limit: int = 50) -> Dict[str, Any]:
    """Return recent pipeline run records with token usage and cost data."""
    db = firestore_helpers._get_fs()
    limit = max(1, min(limit, 500))
    metric_records: Dict[str, Dict[str, Any]] = {}
    run_records: Dict[str, Dict[str, Any]] = {}

    # Primary source: pipeline_metrics (includes tokens/cost/model fields).
    try:
        docs = db.collection("pipeline_metrics").order_by("timestamp", direction="DESCENDING").limit(limit).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None:
                continue
            record = _normalize_pipeline_run(plain, doc.id)
            metric_records[str(record["run_id"])] = record
    except Exception as exc:
        logging.warning("Failed to load pipeline_metrics: %s", exc)

    # Recent runs are the dashboard row source; merge in metrics by run_id so a
    # populated but stale metrics collection does not make current rows look free.
    try:
        docs = db.collection("pipeline_runs").order_by("started_at", direction="DESCENDING").limit(limit).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None:
                continue
            record = _normalize_pipeline_run(plain, doc.id)
            run_records[str(record["run_id"])] = record
    except Exception as exc:
        logging.warning("Failed to load pipeline_runs for metrics merge: %s", exc)

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
    db = firestore_helpers._get_fs()
    records: list[Dict[str, Any]] = []

    try:
        docs = db.collection("pipeline_metrics").order_by("timestamp", direction="DESCENDING").limit(5000).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None:
                continue
            records.append(_normalize_pipeline_run(plain, doc.id))
    except Exception as exc:
        logging.warning("Failed to summarize pipeline_metrics: %s", exc)

    if not records:
        docs = db.collection("pipeline_runs").order_by("started_at", direction="DESCENDING").limit(5000).stream()
        for doc in docs:
            plain = firestore_helpers._doc_to_plain(doc)
            if plain is None:
                continue
            records.append(_normalize_pipeline_run(plain, doc.id))

    if hours is not None and hours > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        records = [r for r in records if _to_epoch_seconds(r.get("timestamp")) >= cutoff]

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
    import gcp_costs as gcp_costs_module

    return gcp_costs_module.get_gcp_costs(days)


# ---------------------------------------------------------------------------
# Alerts (stub — placeholder for domain-aware alert rules)
# ---------------------------------------------------------------------------


@router.get("/alerts", dependencies=[Depends(verify_token)])
async def get_alerts() -> Dict[str, Any]:
    """Return active pipeline alerts (stub — expand with domain rules as needed)."""
    return {"alerts": [], "total": 0, "unacknowledged": 0}


@router.post("/alerts/{alert_id}/acknowledge", dependencies=[Depends(verify_token)])
async def ack_alert(alert_id: str) -> Dict[str, Any]:
    """Acknowledge an alert by ID."""
    return {"ok": True, "alert_id": alert_id}


@router.post("/alerts/acknowledge-all", dependencies=[Depends(verify_token)])
async def ack_all_alerts() -> Dict[str, Any]:
    """Acknowledge all currently active alerts."""
    return {"ok": True, "acknowledged_count": 0}


# ---------------------------------------------------------------------------
# Admin chat proxy
# ---------------------------------------------------------------------------


@router.post("/api/admin-chat", dependencies=[Depends(verify_token)])
async def admin_chat(request: AdminChatRequest) -> Dict[str, Any]:
    """Admin-chat endpoint — forwards messages to OpenRouter with race context."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured")
    model = os.getenv("ADMIN_CHAT_MODEL", _ADMIN_CHAT_MODEL)
    system_content = (
        "You are an AI assistant embedded in the SmarterVote admin dashboard. "
        "You help administrators review races, decide which ones need re-running, "
        "and kick off new pipeline runs with the right settings.\n\n"
        "When you want to queue a run, append exactly one JSON action block at the end:\n"
        'ACTION:{"type":"queue_run","race_ids":["race-id"],"options":{"cheap_mode":true},"description":"One-line description"}\n'
        "When you need clarification, append exactly one question block at the end:\n"
        'QUESTION:{"text":"Your question"}\n'
        "Do not wrap ACTION or QUESTION blocks in markdown. Use exact race IDs."
    )
    race_context = (
        _compact_admin_race_context(request.race_context[:100]) if request.race_context else _load_admin_race_context()
    )
    if race_context:
        system_content += f"\n\nCurrent race context (JSON):\n{json.dumps(race_context, indent=2, default=str)}"
    messages = [{"role": "system", "content": system_content}]
    messages += [{"role": m.role, "content": m.content} for m in request.messages]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://smarter.vote"),
                    "X-Title": os.getenv("OPENROUTER_APP_TITLE", "SmarterVote"),
                },
                json={"model": model, "messages": messages},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            parsed = _parse_admin_chat_reply(reply)
            parsed["race_records"] = _race_records_for_action(parsed.get("action"), race_context)
            parsed["model"] = model
            return parsed
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Chat unavailable: {exc}") from exc
