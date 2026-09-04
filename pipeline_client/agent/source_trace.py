"""Opt-in diagnostics for tracing one issue stance through the pipeline."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

TRACE_ENV = "PIPELINE_ISSUE_SOURCE_TRACE"


def trace_issue_sources(race_json: Dict[str, Any], stage: str, log: Any) -> None:
    """Log one configured issue's sources without adding persistent state.

    ``PIPELINE_ISSUE_SOURCE_TRACE`` uses ``race_id|candidate_name|issue_name``.
    The diagnostic is deliberately opt-in because source objects can make normal
    worker logs noisy. It is intended for following evidence through phase
    boundaries when a stored research audit and the final source list disagree.
    """
    raw_target = os.getenv(TRACE_ENV, "").strip()
    if not raw_target:
        return
    parts = [part.strip() for part in raw_target.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        log("warning", f"Ignoring malformed {TRACE_ENV}; expected race_id|candidate_name|issue_name")
        return

    race_id, candidate_name, issue_name = parts
    if str(race_json.get("id") or "").strip().casefold() != race_id.casefold():
        return

    for candidate in race_json.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("name") or "").strip().casefold() != candidate_name.casefold():
            continue
        issues = candidate.get("issues")
        issue = issues.get(issue_name) if isinstance(issues, dict) else None
        if not isinstance(issue, dict):
            log(
                "info",
                f"ISSUE_SOURCE_TRACE stage={stage} race={race_id} candidate={candidate_name!r} "
                f"issue={issue_name!r} state=missing",
            )
            return
        sources = issue.get("sources") if isinstance(issue.get("sources"), list) else []
        audit = issue.get("research_audit") if isinstance(issue.get("research_audit"), dict) else {}
        log(
            "info",
            f"ISSUE_SOURCE_TRACE stage={stage} race={race_id} candidate={candidate_name!r} "
            f"issue={issue_name!r} source_count={len(sources)} "
            f"audit_source_count={audit.get('source_count')} sources={json.dumps(sources, default=str, sort_keys=True)}",
        )
        return

    log(
        "info",
        f"ISSUE_SOURCE_TRACE stage={stage} race={race_id} candidate={candidate_name!r} state=candidate_missing",
    )
