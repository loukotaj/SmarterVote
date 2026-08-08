from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.models import CanonicalIssue
from shared.pipeline_config import CANONICAL_ISSUE_COUNT, FreshnessConfig
from shared.race_cleanup import forecast_evidence_gaps

_PLACEHOLDER_STANCES = {
    "",
    "draft",
    "fixme",
    "missing",
    "n/a",
    "none",
    "pending",
    "placeholder",
    "tbd",
    "to be determined",
    "todo",
    "unknown",
    "wip",
}
#: Longest a stance opening with a placeholder word may be and still count as junk.
_PLACEHOLDER_PREFIX_MAX_CHARS = 60

_CANONICAL_ISSUES = {issue.value for issue in CanonicalIssue}


def _coerce_datetime(value: Any) -> datetime | None:
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


def compute_freshness(updated_utc: Any) -> str | None:
    updated_at = _coerce_datetime(updated_utc)
    if updated_at is None:
        return None
    config = FreshnessConfig.from_env()
    age_days = (datetime.now(timezone.utc) - updated_at).days
    if age_days <= config.aging_days:
        return "recent"
    if age_days <= config.stale_days:
        return "stale"
    return "old"


def _latest_date(values: List[Any]) -> datetime | None:
    parsed = [date for date in (_coerce_datetime(value) for value in values) if date is not None]
    return max(parsed) if parsed else None


def _section_freshness(race_data: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return independent freshness signals instead of treating a race as one timestamp."""
    section_dates: Dict[str, List[Any]] = {
        "roster": [],
        "issues": [],
        "finance": [],
        "polling": [],
        "forecast": [],
        "voter_resources": [],
    }
    for candidate in candidates:
        for source in candidate.get("roster_sources") or []:
            if isinstance(source, dict):
                section_dates["roster"].append(source.get("last_accessed") or source.get("published_at"))
        for issue in (candidate.get("issues") or {}).values():
            if not isinstance(issue, dict):
                continue
            for source in issue.get("sources") or []:
                if isinstance(source, dict):
                    section_dates["issues"].append(source.get("last_accessed") or source.get("published_at"))
        for key in ("donor_sources", "voting_sources"):
            for source in candidate.get(key) or []:
                if isinstance(source, dict):
                    section_dates["finance"].append(source.get("last_accessed") or source.get("published_at"))
    for poll in race_data.get("polling") or []:
        if isinstance(poll, dict):
            section_dates["polling"].append(
                poll.get("last_accessed") or poll.get("end_date") or poll.get("date") or poll.get("published_at")
            )
    forecast = race_data.get("forecast")
    if isinstance(forecast, dict):
        section_dates["forecast"].append(forecast.get("generated_at"))
    fallback = race_data.get("updated_utc") or race_data.get("generated_at")
    if any(race_data.get(key) for key in ("register_to_vote_url", "find_polling_place_url", "absentee_ballot_url")):
        section_dates["voter_resources"].append(fallback)

    result: Dict[str, Any] = {}
    for section, values in section_dates.items():
        latest = _latest_date(values)
        result[section] = {
            "updated_at": latest.isoformat() if latest else None,
            "status": compute_freshness(latest),
        }
    return result


def extract_quality_grade(race_data: Dict[str, Any]) -> str | None:
    validation_grade = race_data.get("validation_grade")
    if not isinstance(validation_grade, dict):
        return None
    grade = validation_grade.get("grade")
    return str(grade) if grade else None


def _is_missing_image(value: Any) -> bool:
    url = str(value or "").strip().lower()
    return not url or "submitphoto-150px" in url


def _issue_verdict(value: Any) -> tuple[bool, bool, bool]:
    """Return (terminal, substantive, sourced) for one issue record."""
    if not isinstance(value, dict):
        return False, False, False
    stance = str(value.get("stance") or "").strip()
    normalized = stance.strip(".").casefold()
    placeholder_prefix = any(
        normalized == marker or normalized.startswith(f"{marker} ") for marker in _PLACEHOLDER_STANCES if marker
    )
    # The length bound is what keeps a real stance that merely opens with a
    # marker word — "None of the proposed reforms go far enough because..." —
    # from being discarded as a placeholder. Only a short one is junk.
    if (
        not stance
        or normalized in _PLACEHOLDER_STANCES
        or (len(normalized) <= _PLACEHOLDER_PREFIX_MAX_CHARS and placeholder_prefix)
    ):
        return False, False, False
    no_position = "no public position found" in normalized or "no publicly stated position" in normalized
    sources = value.get("sources")
    sourced = isinstance(sources, list) and any(
        isinstance(source, dict) and str(source.get("url") or "").strip() for source in sources
    )
    return True, not no_position, sourced


def _strong_roster_source(source: Any, race_id: Any) -> bool:
    if not isinstance(source, dict) or not source.get("url"):
        return False
    try:
        tier = int(source.get("evidence_tier") or 99)
    except (TypeError, ValueError):
        return False
    return (
        tier <= 2
        and source.get("retrieval_status", "content") == "content"
        and (not source.get("race_id") or source.get("race_id") == race_id)
    )


def build_catalog_health(race_data: Dict[str, Any]) -> Dict[str, Any]:
    """Materialize compact coverage facts used for catalog targeting and repair plans."""
    candidates = [candidate for candidate in race_data.get("candidates", []) if isinstance(candidate, dict)]
    candidate_count = len(candidates)
    issue_slots = candidate_count * CANONICAL_ISSUE_COUNT
    terminal_issues = 0
    substantive_issues = 0
    sourced_issues = 0
    sourced_substantive_issues = 0
    missing_images = 0
    roster_verified_candidates = 0
    roster_strong_evidence_candidates = 0
    finance_complete_candidates = 0
    incumbent_count = 0
    voting_complete_incumbents = 0

    for candidate in candidates:
        missing_images += int(_is_missing_image(candidate.get("image_url")))
        roster_sources = candidate.get("roster_sources")
        roster_verified_candidates += int(isinstance(roster_sources, list) and bool(roster_sources))
        # RaceJSON carries its slug as "id"; only admin catalog records call it
        # "race_id". Reading the wrong key yielded None, so every roster source
        # that names its own race_id — the well-formed ones the roster tools ask
        # for — failed the match and no candidate ever counted as strongly
        # evidenced. Stripping race_id from a source made it "strong", exactly
        # backwards. Accept either shape.
        source_race_id = race_data.get("id") or race_data.get("race_id")
        strong_roster_source = any(_strong_roster_source(source, source_race_id) for source in (roster_sources or []))
        roster_strong_evidence_candidates += int(strong_roster_source)
        issues = candidate.get("issues") if isinstance(candidate.get("issues"), dict) else {}
        for issue_name, issue in issues.items():
            if str(issue_name) not in _CANONICAL_ISSUES:
                continue
            terminal, substantive, sourced = _issue_verdict(issue)
            terminal_issues += int(terminal)
            substantive_issues += int(substantive)
            sourced_issues += int(sourced)
            sourced_substantive_issues += int(substantive and sourced)

        donor_sources = candidate.get("donor_sources")
        has_finance_source = bool(candidate.get("donor_source_url")) or (
            isinstance(donor_sources, list) and bool(donor_sources)
        )
        finance_complete_candidates += int(bool(candidate.get("donor_summary")) and has_finance_source)

        if candidate.get("incumbent"):
            incumbent_count += 1
            voting_sources = candidate.get("voting_sources")
            has_voting_source = bool(candidate.get("voting_source_url")) or (
                isinstance(voting_sources, list) and bool(voting_sources)
            )
            voting_complete_incumbents += int(bool(candidate.get("voting_summary")) and has_voting_source)

    grade_data = race_data.get("validation_grade")
    grade_data = grade_data if isinstance(grade_data, dict) else {}
    grade = str(grade_data.get("grade") or "").upper() or None
    if grade in {"A", "B"} and grade_data.get("passed") is True:
        research_tier = "validated"
    elif grade in {"A", "B", "C", "D", "F"}:
        research_tier = "graded_low"
    elif candidate_count == 0:
        research_tier = "empty"
    elif terminal_issues == 0:
        research_tier = "discovery_only"
    elif terminal_issues < issue_slots:
        research_tier = "partial_research"
    else:
        research_tier = "full_unreviewed"

    forecast = race_data.get("forecast") if isinstance(race_data.get("forecast"), dict) else {}
    forecast_sources = forecast.get("source_urls") if isinstance(forecast.get("source_urls"), list) else []
    forecast_lineage = forecast.get("evidence_lineage") if isinstance(forecast.get("evidence_lineage"), list) else []
    forecast_gaps = forecast_evidence_gaps(race_data)
    forecast_evidence_complete = bool(forecast) and bool(forecast_sources) and not forecast_gaps
    forecast_lineage_complete = bool(forecast_lineage) and all(
        isinstance(item, dict)
        and bool(item.get("claim"))
        and bool(item.get("source_url"))
        and item.get("source_url") in forecast_sources
        for item in forecast_lineage
    )
    pipeline_state = race_data.get("pipeline_state") if isinstance(race_data.get("pipeline_state"), dict) else {}
    run_health = race_data.get("run_health") if isinstance(race_data.get("run_health"), dict) else {}
    section_freshness = _section_freshness(race_data, candidates)
    stale_sections = [section for section, value in section_freshness.items() if value.get("status") in {"stale", "old"}]

    gaps: List[str] = []
    if candidate_count == 0:
        gaps.append("missing_roster")
    if missing_images:
        gaps.append("missing_images")
    if terminal_issues < issue_slots:
        gaps.append("missing_issue_research")
    if substantive_issues and sourced_substantive_issues < substantive_issues:
        gaps.append("unsourced_issue_stances")
    if finance_complete_candidates < candidate_count:
        gaps.append("incomplete_finance")
    if voting_complete_incumbents < incumbent_count:
        gaps.append("incomplete_voting_record")
    if not forecast:
        gaps.append("missing_forecast")
    elif not forecast_evidence_complete:
        gaps.append("forecast_missing_sources")
    if not grade:
        gaps.append("unreviewed")
    elif grade_data.get("passed") is not True:
        gaps.append("validation_failed")

    return {
        "research_tier": research_tier,
        "candidate_count": candidate_count,
        "missing_image_count": missing_images,
        "roster_verified_candidates": roster_verified_candidates,
        "roster_strong_evidence_candidates": roster_strong_evidence_candidates,
        "issue_slot_count": issue_slots,
        "terminal_issue_count": terminal_issues,
        "substantive_issue_count": substantive_issues,
        "sourced_issue_count": sourced_issues,
        "sourced_substantive_issue_count": sourced_substantive_issues,
        "no_position_issue_count": max(0, terminal_issues - substantive_issues),
        "missing_issue_count": max(0, issue_slots - terminal_issues),
        "finance_complete_candidates": finance_complete_candidates,
        "incumbent_count": incumbent_count,
        "voting_complete_incumbents": voting_complete_incumbents,
        "forecast_present": bool(forecast),
        "forecast_source_count": len(forecast_sources),
        "forecast_evidence_complete": forecast_evidence_complete,
        "forecast_lineage_complete": forecast_lineage_complete,
        "forecast_lineage_count": len(forecast_lineage),
        "forecast_evidence_gaps": forecast_gaps,
        "validation_grade": grade,
        "validation_passed": grade_data.get("passed") is True,
        "pipeline_complete": pipeline_state.get("complete") is True,
        "run_health_status": run_health.get("status") or run_health.get("verdict"),
        "section_freshness": section_freshness,
        "stale_sections": stale_sections,
        "gaps": gaps,
    }


def build_candidate_summaries(race_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = race_data.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [
        {
            "name": candidate.get("name", ""),
            "party": candidate.get("party"),
            "incumbent": candidate.get("incumbent", False),
            "image_url": candidate.get("image_url"),
        }
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def build_agent_metrics_summary(race_data: Dict[str, Any]) -> Dict[str, Any] | None:
    agent_metrics = race_data.get("agent_metrics")
    if not isinstance(agent_metrics, dict):
        return None
    return {
        "estimated_usd": agent_metrics.get("estimated_usd"),
        "model": agent_metrics.get("model"),
        "total_tokens": agent_metrics.get("total_tokens"),
    }


def build_forecast_summary(race_data: Dict[str, Any]) -> Dict[str, Any] | None:
    forecast = race_data.get("forecast")
    if not isinstance(forecast, dict):
        return None
    return {
        "predicted_winner_name": forecast.get("predicted_winner_name"),
        "predicted_winner_party": forecast.get("predicted_winner_party"),
        "win_probability": forecast.get("win_probability"),
        "party_probabilities": forecast.get("party_probabilities") or {},
        "margin_estimate": forecast.get("margin_estimate"),
        "rating": forecast.get("rating"),
        "confidence": forecast.get("confidence"),
        "rationale": forecast.get("rationale"),
        "takeaway": forecast.get("takeaway"),
        "key_reasons": forecast.get("key_reasons") or [],
        "uncertainty": forecast.get("uncertainty"),
        "based_on_poll_count": forecast.get("based_on_poll_count", 0),
        "generated_at": forecast.get("generated_at"),
        "model": forecast.get("model"),
        "source_urls": forecast.get("source_urls") or [],
        "market_signals": forecast.get("market_signals") or [],
    }


def build_race_summary_fields(race_id: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    candidates = build_candidate_summaries(race_data)
    updated_utc = race_data.get("updated_utc")
    return {
        "race_id": race_data.get("id") or race_id,
        "title": race_data.get("title"),
        "office": race_data.get("office"),
        "jurisdiction": race_data.get("jurisdiction"),
        "state": race_data.get("state"),
        "election_date": race_data.get("election_date"),
        "updated_utc": updated_utc,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "quality_grade": extract_quality_grade(race_data),
        "freshness": compute_freshness(updated_utc),
        "agent_metrics": build_agent_metrics_summary(race_data),
        "forecast": build_forecast_summary(race_data),
        "catalog_health": build_catalog_health(race_data),
    }


def build_versioned_catalog_fields(prefix: str, race_data: Dict[str, Any]) -> Dict[str, Any]:
    candidates = build_candidate_summaries(race_data)
    updated_utc = race_data.get("updated_utc")
    return {
        f"{prefix}_updated_utc": updated_utc,
        f"{prefix}_candidate_count": len(candidates),
        f"{prefix}_quality_grade": extract_quality_grade(race_data),
        f"{prefix}_catalog_health": build_catalog_health(race_data),
    }
