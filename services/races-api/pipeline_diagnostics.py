"""Build sanitized, self-contained pipeline diagnostic bundles for admin review."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import gcs_helpers
from config import DATA_DIR

from pipeline_client.logging_utils import sanitize_log_data

_DIAGNOSTICS_SCHEMA = "smartervote.pipeline-diagnostics.v1"
_MISSING_STANCE_MARKERS = {"", "draft", "no public position found", "unknown", "n/a"}


_MAX_DIAGNOSTIC_LOGS = 2000


def _plain(doc: Any) -> Optional[Dict[str, Any]]:
    import firestore_helpers

    return firestore_helpers._doc_to_plain(doc)


def _load_draft(race_id: str) -> Optional[Dict[str, Any]]:
    draft = gcs_helpers._gcs_get_race_json(race_id, "drafts")
    if isinstance(draft, dict):
        return draft

    local_path = Path(DATA_DIR).parent / "drafts" / f"{race_id}.json"
    try:
        loaded = json.loads(local_path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _stance_text(issue: Any) -> str:
    if isinstance(issue, str):
        return issue.strip()
    if not isinstance(issue, dict):
        return ""
    for key in ("stance", "position", "summary"):
        value = issue.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _log_sort_key(entry: Dict[str, Any]) -> tuple[float, str]:
    timestamp = entry.get("timestamp")
    if isinstance(timestamp, str):
        try:
            return (datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp(), "")
        except ValueError:
            pass
    legacy_timestamp = entry.get("ts")
    if isinstance(legacy_timestamp, (int, float)):
        return (float(legacy_timestamp), "")
    return (0.0, str(entry.get("id") or ""))


def _draft_summary(draft: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(draft, dict):
        return None

    candidates = [candidate for candidate in draft.get("candidates") or [] if isinstance(candidate, dict)]
    candidate_summaries = []
    total_issues = 0
    missing_stances = 0
    issue_sources = 0
    placeholder_stances = 0

    for candidate in candidates:
        issues = candidate.get("issues") if isinstance(candidate.get("issues"), dict) else {}
        candidate_missing = 0
        candidate_issue_sources = 0
        for issue in issues.values():
            stance = _stance_text(issue)
            normalized = stance.casefold()
            if normalized in _MISSING_STANCE_MARKERS:
                candidate_missing += 1
                missing_stances += 1
                if normalized == "draft":
                    placeholder_stances += 1
            if isinstance(issue, dict) and issue.get("sources"):
                candidate_issue_sources += 1
                issue_sources += 1
        total_issues += len(issues)
        candidate_summaries.append(
            {
                "name": candidate.get("name"),
                "issue_count": len(issues),
                "missing_stance_count": candidate_missing,
                "issues_with_sources": candidate_issue_sources,
                "has_summary": bool(str(candidate.get("summary") or "").strip()),
                "summary_source_count": len(candidate.get("summary_sources") or []),
                "roster_source_count": len(candidate.get("roster_sources") or []),
                "has_image": bool(candidate.get("image_url")),
                "has_donor_summary": bool(candidate.get("donor_summary")),
                "has_voting_summary": bool(candidate.get("voting_summary")),
            }
        )

    grade = draft.get("validation_grade") if isinstance(draft.get("validation_grade"), dict) else {}
    state = draft.get("pipeline_state") if isinstance(draft.get("pipeline_state"), dict) else {}
    return {
        "candidate_count": len(candidates),
        "candidate_names": [candidate.get("name") for candidate in candidates],
        "issue_count": total_issues,
        "missing_stance_count": missing_stances,
        "placeholder_stance_count": placeholder_stances,
        "issues_with_sources": issue_sources,
        "validation_grade": grade,
        "pipeline_complete": state.get("complete"),
        "remaining_steps": state.get("remaining_steps") or [],
        "agent_metrics": draft.get("agent_metrics") if isinstance(draft.get("agent_metrics"), dict) else None,
        "candidates": candidate_summaries,
    }


def build_diagnostics_bundle(run_id: str, db: Any) -> Optional[Dict[str, Any]]:
    """Combine run, queue, logs, race state, and draft output into one export."""
    run_ref = db.collection("pipeline_runs").document(run_id)
    run = _plain(run_ref.get())
    if run is None:
        return None

    log_query = run_ref.collection("logs").order_by("__name__").limit(_MAX_DIAGNOSTIC_LOGS)
    logs = [_plain(doc) for doc in log_query.stream()]
    logs = [entry for entry in logs if entry is not None]

    logs.sort(key=_log_sort_key)
    queue_docs = db.collection("pipeline_queue").where("run_id", "==", run_id).limit(100).stream()
    queue_items = [item for item in (_plain(doc) for doc in queue_docs) if item is not None]

    race_id = str(run.get("race_id") or (run.get("payload") or {}).get("race_id") or "")
    race_record = _plain(db.collection("races").document(race_id).get()) if race_id else None
    draft = _load_draft(race_id) if race_id else None

    level_counts = Counter(str(entry.get("level") or "info").lower() for entry in logs)
    event_counts = Counter(
        str((entry.get("extra") or {}).get("event"))
        for entry in logs
        if isinstance(entry.get("extra"), dict) and (entry.get("extra") or {}).get("event")
    )
    timeline = [
        {
            "timestamp": entry.get("timestamp"),
            "level": entry.get("level"),
            "step": entry.get("step"),
            "message": entry.get("message"),
            "event": (entry.get("extra") or {}).get("event"),
            "details": entry.get("extra") or {},
        }
        for entry in logs
        if isinstance(entry.get("extra"), dict) and (entry.get("extra") or {}).get("event") != "agent_log"
    ]

    debug_enabled = bool(run.get("debug_mode") or (run.get("options") or {}).get("debug_mode"))
    warnings = []
    if not debug_enabled:
        warnings.append("This run did not enable debug_mode; structured timeline detail may be incomplete.")
    if draft is None:
        warnings.append("No current draft artifact was available for this race.")
    log_stats = run.get("log_stats") if isinstance(run.get("log_stats"), dict) else {}
    if log_stats.get("dropped") or log_stats.get("truncated"):
        warnings.append("Some run logs were dropped or truncated; inspect run.log_stats.")
    if len(logs) == _MAX_DIAGNOSTIC_LOGS:
        warnings.append(f"Log export reached the {_MAX_DIAGNOSTIC_LOGS}-document safety cap and may be incomplete.")
    if run.get("status") in {"pending", "running"}:
        warnings.append("The run is still active; export again after it reaches a terminal status.")

    bundle = {
        "schema": _DIAGNOSTICS_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "race_id": race_id or None,
        "debug_mode": debug_enabled,
        "warnings": warnings,
        "summary": {
            "status": run.get("status"),
            "log_count": len(logs),
            "log_levels": dict(level_counts),
            "log_read_cap": _MAX_DIAGNOSTIC_LOGS,
            "event_counts": dict(event_counts),
            "queue_item_count": len(queue_items),
            "draft_available": draft is not None,
            "draft_quality": _draft_summary(draft),
        },
        "timeline": timeline,
        "run": run,
        "queue_items": queue_items,
        "race_record": race_record,
        "logs": logs,
        "artifacts": {"draft": draft},
    }
    return sanitize_log_data(bundle)
